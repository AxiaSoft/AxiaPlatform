import json
import sys
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import app
import db


class AdminApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_db_path = db.DB_PATH
        cls.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(cls.temp.name) / 'admin-api.sqlite3'
        db.init()
        conn = db.connect()
        conn.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',
                     ('Test Administrator', 'admin@example.test', app.hash_password('admin test password'), 'admin'))
        conn.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',
                     ('Test Customer', 'customer@example.test', app.hash_password('customer test password'), 'customer'))
        conn.commit()
        cls.customer_id = conn.execute("SELECT id FROM users WHERE email='customer@example.test'").fetchone()['id']
        # The shipped catalog is empty by design, so the fixture creates the
        # product it needs (including a preview link) instead of assuming a seed.
        cur_product = conn.execute(
            "INSERT INTO products(slug,title,category,summary,description,features,technologies,github_url) "
            "VALUES(?,?,?,?,?,?,?,?)",
            ('northstar-corporate', 'Northstar Corporate', 'Websites',
             'A confident digital home for ambitious teams.', 'Test description.',
             '["Responsive pages"]', '["Next.js"]', 'https://github.com/AxiaSoft/northstar'))
        cls.product_id = cur_product.lastrowid
        cur = conn.execute('INSERT INTO orders(number,user_id,product_id,name,email,phone,description) VALUES(?,?,?,?,?,?,?)',
                           ('AX-TEST-123456', cls.customer_id, cls.product_id, 'Test Customer', 'customer@example.test', '+4900000000', 'A test project request with sufficient detail.'))
        cls.order_id = cur.lastrowid
        conn.execute('INSERT INTO order_history(order_id,status,note) VALUES(?,?,?)', (cls.order_id, 'Submitted', 'Test request received'))
        conn.commit()
        conn.close()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        db.DB_PATH = cls.original_db_path
        cls.temp.cleanup()

    def setUp(self):
        conn = db.connect()
        conn.execute("UPDATE users SET active=1 WHERE email='customer@example.test'")
        conn.execute("DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE email='customer@example.test')")
        conn.commit()
        conn.close()
        self.admin = build_opener(HTTPCookieProcessor(CookieJar()))
        self.customer = build_opener(HTTPCookieProcessor(CookieJar()))
        self.csrf = self.login(self.admin, 'admin@example.test', 'admin test password')
        self.login(self.customer, 'customer@example.test', 'customer test password')

    def request(self, opener, path, method='GET', payload=None, csrf=None):
        data = None if payload is None else json.dumps(payload).encode()
        headers = {'Content-Type': 'application/json'}
        if csrf:
            headers['X-CSRF-Token'] = csrf
        req = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with opener.open(req, timeout=4) as response:
                return response.status, json.loads(response.read().decode())
        except HTTPError as error:
            return error.code, json.loads(error.read().decode())

    def login(self, opener, email, password):
        _, data = self.request(opener, '/api/login', 'POST', {'email': email, 'password': password})
        status, session = self.request(opener, '/api/me')
        self.assertEqual(status, 200)
        self.assertIsNotNone(session['user'])
        return session['csrf']

    def test_admin_customer_list_is_role_gated_and_does_not_expose_passwords(self):
        status, _ = self.request(build_opener(), '/api/admin/customers')
        self.assertEqual(status, 403)
        status, data = self.request(self.customer, '/api/admin/customers')
        self.assertEqual(status, 403)
        status, data = self.request(self.admin, '/api/admin/customers')
        self.assertEqual(status, 200)
        self.assertEqual(data['total'], 1)
        customer = data['customers'][0]
        self.assertEqual(customer['email'], 'customer@example.test')
        self.assertNotIn('password_hash', customer)

    def test_order_history_is_admin_only_and_scoped_by_order(self):
        path = f'/api/admin/orders/{self.order_id}/history'
        self.assertEqual(self.request(self.customer, path)[0], 403)
        status, data = self.request(self.admin, path)
        self.assertEqual(status, 200)
        self.assertEqual(data[0]['status'], 'Submitted')

    def test_product_edits_require_csrf_and_keep_complete_catalog_fields(self):
        payload = {'id': self.product_id, 'title': 'Updated test product', 'slug': 'northstar-corporate',
                   'summary': 'Updated summary', 'description': 'Updated description for this project concept.',
                   'price_label': 'Request a quote', 'category': 'Websites', 'status': 'available',
                   'cover': '/uploads/covers/abc123.png', 'features': ['One', 'Two'], 'technologies': ['Python'], 'published': True}
        self.assertEqual(self.request(self.admin, '/api/admin/products', 'PUT', payload)[0], 403)
        status, _ = self.request(self.admin, '/api/admin/products', 'PUT', payload, self.csrf)
        self.assertEqual(status, 200)
        products = self.request(self.admin, '/api/admin/overview')[1]['products']
        updated = next(p for p in products if p['id'] == self.product_id)
        self.assertEqual(updated['features'], ['One', 'Two'])
        self.assertEqual(updated['technologies'], ['Python'])

    def test_github_preview_link_is_validated_and_published(self):
        base = {'title': 'Preview Product', 'slug': 'preview-product', 'category': 'Websites',
                'summary': 'Summary', 'description': 'A description long enough to pass.',
                'status': 'available', 'features': [], 'technologies': [], 'published': True}

        # Anything that is not a plain https URL must be refused outright.
        for bad in ('javascript:alert(1)', 'data:text/html,<script>alert(1)</script>',
                    'http://insecure.example.test', '//protocol-relative.example.test',
                    'example.test/no-scheme'):
            payload = dict(base, github_url=bad)
            status, body = self.request(self.admin, '/api/admin/products', 'POST', payload, self.csrf)
            self.assertEqual(status, 400, f'{bad} should be rejected, got {status} {body}')

        # A real link is stored and handed back to the storefront.
        payload = dict(base, github_url='https://github.com/AxiaSoft/preview-product')
        status, body = self.request(self.admin, '/api/admin/products', 'POST', payload, self.csrf)
        self.assertEqual(status, 201, body)
        created = next(p for p in self.request(self.admin, '/api/admin/overview')[1]['products']
                       if p['slug'] == 'preview-product')
        self.assertEqual(created['github_url'], 'https://github.com/AxiaSoft/preview-product')
        guest = build_opener(HTTPCookieProcessor(CookieJar()))
        public = next(p for p in self.request(guest, '/api/products')[1]
                      if p['slug'] == 'preview-product')
        self.assertEqual(public['github_url'], 'https://github.com/AxiaSoft/preview-product')

        # Blank is allowed - the storefront then shows its built-in preview.
        payload = dict(base, slug='no-link-product', github_url='')
        self.assertEqual(self.request(self.admin, '/api/admin/products', 'POST', payload, self.csrf)[0], 201)

    def test_settings_are_validated_persisted_and_publicly_readable(self):
        # The storefront reads the settings anonymously.
        status, public_before = self.request(build_opener(), '/api/site')
        self.assertEqual(status, 200)
        self.assertIs(public_before['settings']['show_catalog'], True)
        self.assertEqual(public_before['settings']['hero_title'], 'Building digital experiences.')

        # Only administrators may write them.
        status, _ = self.request(self.customer, '/api/admin/settings', 'PUT',
                                 {'hero_title': 'Hijacked'}, self.csrf)
        self.assertEqual(status, 403)

        # A valid partial update merges into the stored document.
        status, body = self.request(self.admin, '/api/admin/settings', 'PUT',
                                    {'hero_title': 'Calm software.', 'show_services': False,
                                     'announcement_enabled': True,
                                     'announcement_text': 'Launch week'}, self.csrf)
        self.assertEqual(status, 200, body)
        self.assertEqual(body['settings']['hero_title'], 'Calm software.')
        self.assertIs(body['settings']['show_services'], False)
        self.assertIs(body['settings']['announcement_enabled'], True)
        # untouched values keep their defaults
        self.assertEqual(body['settings']['hero_accent'], "Engineering what's next.")

        status, public_after = self.request(build_opener(), '/api/site')
        self.assertEqual(public_after['settings']['hero_title'], 'Calm software.')
        self.assertIs(public_after['settings']['show_services'], False)

        # Bad values are refused with a field-level error, not silently dropped.
        status, rejected = self.request(self.admin, '/api/admin/settings', 'PUT',
                                        {'contact_email': 'not-an-address'}, self.csrf)
        self.assertEqual(status, 400)
        self.assertIn('contact_email', rejected['fields'])
        for payload in ({'announcement_link': 'javascript:alert(1)'},
                        {'announcement_link': 'http://insecure.test'},
                        {'default_theme': 'neon'},
                        {'not_a_setting': 1}):
            status, _ = self.request(self.admin, '/api/admin/settings', 'PUT', payload, self.csrf)
            self.assertEqual(status, 400, payload)

        # The change is audited.
        conn = db.connect()
        audited = conn.execute("SELECT count(*) n FROM audit_logs WHERE action='settings'").fetchone()['n']
        conn.close()
        self.assertGreaterEqual(audited, 1)

        # Restore the defaults so other tests see the shipped copy.
        self.request(self.admin, '/api/admin/settings', 'PUT',
                     {'hero_title': 'Building digital experiences.', 'show_services': True,
                      'announcement_enabled': False, 'announcement_text': ''}, self.csrf)

    def test_products_can_be_featured_and_ordered(self):
        base = {'title': 'Ordered Product', 'slug': 'ordered-product', 'category': 'Websites',
                'summary': 'Summary', 'description': 'A description long enough to pass.',
                'status': 'available', 'features': [], 'technologies': [], 'published': True}
        created = []
        for index, (slug, featured, position) in enumerate(
                [('ordered-a', False, 300), ('ordered-b', True, 200), ('ordered-c', False, 100)]):
            payload = dict(base, slug=slug, featured=featured, position=position,
                           title=f'Ordered {slug[-1].upper()}')
            status, body = self.request(self.admin, '/api/admin/products', 'POST', payload, self.csrf)
            self.assertEqual(status, 201, body)
            created.append(body['id'])

        # Editing keeps the flags.
        status, _ = self.request(self.admin, '/api/admin/products', 'PUT',
                                 {'id': created[2], 'featured': True, 'position': 5}, self.csrf)
        self.assertEqual(status, 200)
        products = {p['slug']: p for p in self.request(self.admin, '/api/admin/overview')[1]['products']}
        self.assertEqual(products['ordered-b']['position'], 200)
        self.assertEqual(products['ordered-c']['position'], 5)
        self.assertEqual(products['ordered-c']['featured'], 1)

        # The public catalog leads with featured products and then follows position.
        guest = build_opener(HTTPCookieProcessor(CookieJar()))
        order = [p['slug'] for p in self.request(guest, '/api/products')[1]
                 if p['slug'].startswith('ordered-')]
        featured = [s for s in order
                    if products[s]['featured']]
        self.assertEqual(len(featured), 2)
        self.assertEqual(order[:2], featured)
        self.assertEqual(order[-1], 'ordered-a')

        # A non-numeric position is refused rather than stored as zero.
        status, _ = self.request(self.admin, '/api/admin/products', 'PUT',
                                 {'id': created[0], 'position': 'north'}, self.csrf)
        self.assertEqual(status, 400)

    def test_customer_suspension_revokes_sessions_and_is_audited(self):
        status, data = self.request(self.admin, '/api/admin/customers/status', 'PUT',
                                    {'id': self.customer_id, 'active': False}, self.csrf)
        self.assertEqual(status, 200)
        conn = db.connect()
        active = conn.execute('SELECT active FROM users WHERE id=?', (self.customer_id,)).fetchone()['active']
        sessions = conn.execute('SELECT count(*) n FROM sessions WHERE user_id=?', (self.customer_id,)).fetchone()['n']
        audit = conn.execute("SELECT count(*) n FROM audit_logs WHERE action='customer_access'").fetchone()['n']
        conn.close()
        self.assertEqual(active, 0)
        self.assertEqual(sessions, 0)
        self.assertGreaterEqual(audit, 1)


    # ---- blog ---------------------------------------------------------- #
    def test_drafts_never_reach_the_public_feed(self):
        status, data = self.request(self.admin, '/api/admin/articles', 'POST', {
            'title': 'A draft about caching', 'slug': 'about-caching',
            'summary': 'Not published yet.', 'body': 'x' * 120, 'status': 'draft',
        }, self.csrf)
        self.assertEqual(status, 201)
        status, feed = self.request(build_opener(), '/api/articles')
        self.assertEqual(status, 200)
        self.assertNotIn('about-caching', [a['slug'] for a in feed['articles']])

    def test_publishing_exposes_the_article_with_rendered_html(self):
        status, created = self.request(self.admin, '/api/admin/articles', 'POST', {
            'title': 'Shipping a small site', 'slug': 'shipping-small',
            'summary': 'How a small site actually ships.', 'tags': ['process'],
            'body': '## First\n\nWrite **clearly** and ship the whole thing.\n\n- one\n- two', 'status': 'published',
        }, self.csrf)
        self.assertEqual(status, 201)
        status, item = self.request(build_opener(), '/api/articles/shipping-small')
        self.assertEqual(status, 200)
        # '##' becomes an <h3> because the article page owns the single <h1>
        # and '#' becomes <h2>, so a writer never competes with the headline.
        self.assertIn('<h3>First</h3>', item['html'])
        self.assertIn('<strong>clearly</strong>', item['html'])
        self.assertIn('<li>one</li>', item['html'])
        self.assertGreaterEqual(item['reading_minutes'], 1)

    def test_a_duplicate_slug_is_refused(self):
        payload = {'title': 'Unique title here', 'slug': 'unique-slug',
                   'summary': 's', 'body': 'x' * 100, 'status': 'draft'}
        self.assertEqual(self.request(self.admin, '/api/admin/articles', 'POST', payload, self.csrf)[0], 201)
        self.assertEqual(self.request(self.admin, '/api/admin/articles', 'POST', payload, self.csrf)[0], 409)

    def test_article_writes_are_role_gated_and_csrf_protected(self):
        # Signed out: no listing, no writes.
        self.assertEqual(self.request(build_opener(), '/api/admin/articles')[0], 403)
        # A customer session is not an administrator session.
        self.assertEqual(self.request(self.customer, '/api/admin/articles')[0], 403)
        # Signed in, but a write without the session's CSRF token is refused.
        status, _ = self.request(self.admin, '/api/admin/articles', 'DELETE', {'id': 999999})
        self.assertEqual(status, 403)
        # The same write with the token is allowed through to the handler.
        status, _ = self.request(self.admin, '/api/admin/articles', 'DELETE', {'id': 999999}, self.csrf)
        self.assertEqual(status, 404)

    def test_the_support_agent_answers_without_a_session(self):
        status, data = self.request(build_opener(), '/api/agent', 'POST',
                                    {'question': 'how do I request a product?'})
        self.assertEqual(status, 200)
        self.assertIn('source', data)
        self.assertTrue(data['answer'])

    def test_the_agent_rejects_an_empty_question(self):
        status, _ = self.request(build_opener(), '/api/agent', 'POST', {'question': '   '})
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()
