"""End-to-end API tests, including regression tests for the SQLite lock wedge.

The critical regression: a failed write (duplicate email, duplicate slug, bad
payload) used to leave an uncommitted transaction open, which made every later
write fail with "database is locked" until the process garbage-collected the
leaked connection. These tests lock that behaviour down.
"""
import json
import sys
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import app
import db


class ApiFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.original_db_path = db.DB_PATH
        db.DB_PATH = Path(cls.temp.name) / 'flow.sqlite3'
        db.init()
        conn = db.connect()
        conn.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',
                     ('Flow Administrator', 'admin@flow.test', app.hash_password('flow admin password'), 'admin'))
        # The shipped catalog is empty by design (products come from the admin
        # console), so the journey test's own fixtures are created here.
        conn.executemany(
            'INSERT INTO products(slug,title,category,summary,description,features,technologies,status,price_label,github_url) '
            'VALUES(?,?,?,?,?,?,?,?,?,?)',
            [('flow-website', 'Flow Website', 'Websites', 'Summary', 'Description', '[]', '[]',
              'available', 'Request a quote', 'https://github.com/AxiaSoft/flow-website'),
             ('flow-aurion', 'Flow AURION', 'Aurion', 'Summary', 'Description', '[]', '[]',
              'showcase', 'Presentation only', '')])
        conn.close()
        cls.servers = []
        cls.server = app.AxiServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = 'http://127.0.0.1:%d' % cls.server.server_address[1]
        app.RATE_LIMITS.update({k: 10_000 for k in app.RATE_LIMITS})
        app.LOGIN_LOCKOUT = app.Lockout(1_000, 1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        db.DB_PATH = cls.original_db_path
        cls.temp.cleanup()

    def setUp(self):
        app.RATE.reset()
        app.LOGIN_LOCKOUT = app.Lockout(1_000, 1)
        self.anon = self.opener()
        self.customer = self.opener()
        self.admin = self.opener()
        self.admin_csrf = self.login(self.admin, 'admin@flow.test', 'flow admin password')

    # -- helpers --------------------------------------------------------- #
    def opener(self):
        return build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, opener, path, method='GET', payload=None, csrf=None, raw=None):
        data = raw if raw is not None else (None if payload is None else json.dumps(payload).encode())
        headers = {'Content-Type': 'application/json'}
        if csrf:
            headers['X-CSRF-Token'] = csrf
        req = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with opener.open(req, timeout=15) as response:
                body = response.read().decode()
                return response.status, json.loads(body) if body else {}
        except HTTPError as error:
            body = error.read().decode()
            try:
                return error.code, json.loads(body)
            except Exception:
                return error.code, {'raw': body}

    def login(self, opener, email, password):
        status, _ = self.request(opener, '/api/login', 'POST', {'email': email, 'password': password})
        self.assertEqual(status, 200)
        status, session = self.request(opener, '/api/me')
        self.assertEqual(status, 200)
        self.assertIsNotNone(session['user'])
        return session['csrf']

    def csrf_for(self, opener):
        return self.request(opener, '/api/me')[1]['csrf']

    def newest_writable_proof(self):
        """A full create-then-commit cycle; fails loudly if the database is wedged."""
        _, products = self.request(self.anon, '/api/products')
        website = next(p for p in products if p['category'] == 'Websites')
        status, body = self.request(
            self.customer, '/api/orders', 'POST',
            {'product_id': website['id'], 'name': 'Proof Buyer', 'email': 'proof@flow.test',
             'phone': '+490000000', 'description': 'A complete description used to prove writes still work.'},
            self.csrf_for(self.customer))
        return status, body

    # -- the regression formerly known as "database is locked" ------------ #
    def test_duplicate_registration_does_not_wedge_the_database(self):
        payload = {'name': 'Wedged User', 'email': 'wedge@flow.test', 'password': 'correct horse battery'}
        first, _ = self.request(self.anon, '/api/register', 'POST', payload)
        self.assertEqual(first, 201)
        duplicate, body = self.request(self.opener(), '/api/register', 'POST', payload)
        self.assertEqual(duplicate, 409, body)
        # A brand-new signup must still work immediately after the failed write.
        for n in range(3):
            status, body = self.request(self.opener(), '/api/register', 'POST',
                                        {'name': 'Fresh %d' % n, 'email': 'fresh%d@flow.test' % n,
                                         'password': 'correct horse battery'})
            self.assertEqual(status, 201, 'signup %d failed after a 409: %s' % (n, body))

    def test_duplicate_product_slug_does_not_wedge_the_database(self):
        product = {'slug': 'wedge-product', 'title': 'Wedge', 'category': 'Websites',
                   'summary': 'Summary text', 'description': 'Description text', 'features': ['a'],
                   'technologies': ['b']}
        status, body = self.request(self.admin, '/api/admin/products', 'POST', product, self.admin_csrf)
        self.assertEqual(status, 201, body)
        created_id = body['id']
        status, body = self.request(self.admin, '/api/admin/products', 'POST', product, self.admin_csrf)
        self.assertEqual(status, 409, body)
        # Unpublish must work after the rejected insert.
        status, body = self.request(self.admin, '/api/admin/products', 'DELETE', {'id': created_id}, self.admin_csrf)
        self.assertEqual(status, 200, body)
        # And a new product can still be created.
        second = dict(product, slug='wedge-product-two')
        status, body = self.request(self.admin, '/api/admin/products', 'POST', second, self.admin_csrf)
        self.assertEqual(status, 201, body)

    def test_failed_writes_leave_no_open_transaction(self):
        payload = {'name': 'Tx Check', 'email': 'tx@flow.test', 'password': 'correct horse battery'}
        self.request(self.anon, '/api/register', 'POST', payload)
        self.request(self.opener(), '/api/register', 'POST', payload)  # 409
        self.request(self.admin, '/api/admin/products', 'POST',
                     {'slug': 'bad slug!', 'title': 'x', 'category': 'Websites',
                      'summary': 's', 'description': 'd'}, self.admin_csrf)  # 400
        self.request(self.admin, '/api/admin/orders/status', 'PUT', {'id': 999999, 'status': 'Nonsense'},
                     self.admin_csrf)  # 400
        conn = db.connect()
        try:
            self.assertFalse(conn.in_transaction)
            conn.execute("INSERT INTO audit_logs(actor_id,action,entity,entity_id) VALUES(NULL,'probe','test','1')")
        finally:
            conn.close()

    # -- request validation ---------------------------------------------- #
    def test_rejects_oversized_and_malformed_bodies(self):
        status, _ = self.request(self.anon, '/api/register', 'POST', raw=b'x' * 200_000)
        self.assertEqual(status, 413)
        status, _ = self.request(self.anon, '/api/register', 'POST', raw=b'not json')
        self.assertEqual(status, 400)
        status, _ = self.request(self.anon, '/api/register', 'POST', raw=b'[' * 300)
        self.assertEqual(status, 400)
        status, _ = self.request(self.anon, '/api/register', 'POST', raw=b'[1,2,3]')
        self.assertEqual(status, 400)

    def test_password_length_is_bounded(self):
        status, _ = self.request(self.anon, '/api/register', 'POST',
                                 {'name': 'Long Password', 'email': 'long@flow.test', 'password': 'x' * 5000})
        self.assertEqual(status, 400)

    def test_unsupported_methods_are_refused(self):
        for method in ('TRACE', 'PATCH', 'OPTIONS'):
            status, _ = self.request(self.anon, '/api/me', method)
            self.assertEqual(status, 405, method)

    def test_path_traversal_and_directory_listing_are_blocked(self):
        for path in ('/../server/app.py', '/..%2fserver%2fapp.py', '/%2e%2e/server/db.py', '/brand/'):
            status, body = self.request(self.anon, path)
            text = json.dumps(body)
            self.assertNotIn('import ', text)
            self.assertNotIn('Index of', text)
            self.assertIn(status, (400, 404), path)

    def test_security_headers_present(self):
        status, _ = self.request(self.anon, '/api/health')
        self.assertEqual(status, 200)
        req = Request(self.base + '/api/health')
        with self.anon.open(req, timeout=10) as response:
            headers = response.headers
        self.assertEqual(headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(headers.get('X-Frame-Options'), 'DENY')
        self.assertIn("default-src 'self'", headers.get('Content-Security-Policy', ''))
        self.assertNotIn('SimpleHTTP', headers.get('Server', ''))

    # -- core customer journeys ------------------------------------------ #
    def test_customer_journey_order_ticket_and_refund(self):
        status, body = self.request(self.customer, '/api/register', 'POST',
                                    {'name': 'Journey User', 'email': 'journey@flow.test',
                                     'phone': '+4912345', 'password': 'correct horse battery'})
        self.assertEqual(status, 201, body)
        csrf = self.csrf_for(self.customer)

        _, products = self.request(self.anon, '/api/products')
        website = next(p for p in products if p['category'] == 'Websites')
        aurion = next(p for p in products if p['category'] == 'Aurion')

        status, body = self.request(self.customer, '/api/orders', 'POST',
                                    {'product_id': website['id'], 'name': 'Journey User',
                                     'email': 'journey@flow.test', 'phone': '+491234567',
                                     'description': 'We need a corporate site with clear messaging.'}, csrf)
        self.assertEqual(status, 201, body)
        self.assertTrue(body['number'].startswith('AX-'))

        status, body = self.request(self.customer, '/api/orders', 'POST',
                                    {'product_id': aurion['id'], 'name': 'Journey',
                                     'email': 'journey@flow.test', 'phone': '+491234567',
                                     'description': 'x' * 30}, csrf)
        self.assertEqual(status, 400, 'Aurion must not be orderable')

        _, orders = self.request(self.customer, '/api/orders')
        mine = [o for o in orders if o['email'] == 'journey@flow.test']
        self.assertEqual(len(mine), 1)
        order_id = mine[0]['id']

        status, body = self.request(self.customer, '/api/refunds', 'POST',
                                    {'order_id': order_id, 'reason': 'Not the right fit'}, csrf)
        self.assertEqual(status, 201, body)
        status, body = self.request(self.customer, '/api/refunds', 'POST',
                                    {'order_id': order_id, 'reason': 'Again please'}, csrf)
        self.assertEqual(status, 409, body)

        status, body = self.request(self.customer, '/api/support', 'POST',
                                    {'subject': 'Need help', 'message': 'Please help with my order.'}, csrf)
        self.assertEqual(status, 201, body)

        # Admin side sees and updates it
        status, overview = self.request(self.admin, '/api/admin/overview')
        self.assertEqual(status, 200)
        status, body = self.request(self.admin, '/api/admin/orders/status', 'PUT',
                                    {'id': order_id, 'status': 'In Development', 'note': 'Kickoff'},
                                    self.admin_csrf)
        self.assertEqual(status, 200, body)
        status, history = self.request(self.admin, '/api/admin/orders/%d/history' % order_id)
        self.assertEqual([h['status'] for h in history], ['Submitted', 'In Development'])

        status, _ = self.request(self.admin, '/api/admin/orders/status', 'PUT',
                                 {'id': order_id, 'status': 'Nonsense'}, self.admin_csrf)
        self.assertEqual(status, 400)

    def test_session_suspension_revokes_access(self):
        self.request(self.customer, '/api/register', 'POST',
                     {'name': 'Suspend Me', 'email': 'suspend@flow.test', 'password': 'correct horse battery'})
        status, session = self.request(self.customer, '/api/me')
        customer_id = session['user']['id']
        status, body = self.request(self.admin, '/api/admin/customers/status', 'PUT',
                                    {'id': customer_id, 'active': False}, self.admin_csrf)
        self.assertEqual(status, 200, body)
        status, session = self.request(self.customer, '/api/me')
        self.assertIsNone(session['user'])

    def test_rate_limiter_ignores_query_string_variations(self):
        app.RATE.reset()
        app.RATE_LIMITS['auth'] = 3
        try:
            codes = []
            for n in range(6):
                status, _ = self.request(self.opener(), '/api/login?nonce=%d' % n, 'POST',
                                         {'email': 'nobody@flow.test', 'password': 'wrong password'})
                codes.append(status)
            self.assertEqual(codes.count(429), 3, codes)
        finally:
            app.RATE_LIMITS['auth'] = 10_000

    def test_login_lockout_after_repeated_failures(self):
        app.LOGIN_LOCKOUT = app.Lockout(3, 60)
        self.request(self.opener(), '/api/register', 'POST',
                     {'name': 'Locked User', 'email': 'lock@flow.test', 'password': 'correct horse battery'})
        codes = []
        for _ in range(4):
            status, _ = self.request(self.opener(), '/api/login', 'POST',
                                     {'email': 'lock@flow.test', 'password': 'wrong password'})
            codes.append(status)
        self.assertEqual(codes[-1], 429, codes)
        status, _ = self.request(self.opener(), '/api/login', 'POST',
                                 {'email': 'lock@flow.test', 'password': 'correct horse battery'})
        self.assertEqual(status, 429, 'lockout must hold even for the correct password')


class LimiterUnitTests(unittest.TestCase):
    def test_rate_limiter_window_and_retry_after(self):
        limiter = app.RateLimiter()
        for _ in range(3):
            allowed, _, _ = limiter.hit('b', 'client', 3, 60)
            self.assertTrue(allowed)
        allowed, retry, remaining = limiter.hit('b', 'client', 3, 60)
        self.assertFalse(allowed)
        self.assertGreater(retry, 0)
        self.assertEqual(remaining, 0)

    def test_rate_limiter_buckets_are_independent_and_bounded(self):
        limiter = app.RateLimiter(max_keys=10, vacuum_every=5)
        for n in range(50):
            limiter.hit('b', 'client-%d' % n, 5, 60)
        self.assertLessEqual(limiter.size, 10)
        limiter2 = app.RateLimiter()
        self.assertTrue(limiter2.hit('read', 'c', 1, 60)[0])
        self.assertTrue(limiter2.hit('write', 'c', 1, 60)[0])

    def test_huge_client_address_is_hashed_not_stored_raw(self):
        guard = app.ConcurrencyGuard(4, 2)
        huge = 'X' * 5000
        self.assertTrue(guard.acquire(huge))
        self.assertTrue(guard.acquire(huge))
        self.assertFalse(guard.acquire(huge))
        guard.release(huge)
        guard.release(huge)
        self.assertEqual(guard.active, 0)
        self.assertFalse(any(isinstance(k, str) and len(k) > 200 for k in guard._active))

    def test_lockout_expires(self):
        lock = app.Lockout(2, 1)
        self.assertFalse(lock.register_failure('x')[0])
        self.assertTrue(lock.register_failure('x')[0])
        self.assertTrue(lock.is_locked('x')[0])
        import time
        time.sleep(1.1)
        self.assertFalse(lock.is_locked('x')[0])

    def test_ip_normalization(self):
        from security import normalize_ip
        self.assertEqual(normalize_ip('::ffff:127.0.0.1'), '127.0.0.1')
        self.assertEqual(normalize_ip(' 10.0.0.1 '), '10.0.0.1')
        self.assertEqual(normalize_ip(''), 'unresolved')
        self.assertEqual(len(normalize_ip('X' * 5000)), len('sha256:') + 64)


if __name__ == '__main__':
    unittest.main()
