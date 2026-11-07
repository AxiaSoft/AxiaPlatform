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
        cls.product_id = conn.execute("SELECT id FROM products WHERE slug='northstar-corporate'").fetchone()['id']
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
                   'cover': 'web', 'features': ['One', 'Two'], 'technologies': ['Python'], 'published': True}
        self.assertEqual(self.request(self.admin, '/api/admin/products', 'PUT', payload)[0], 403)
        status, _ = self.request(self.admin, '/api/admin/products', 'PUT', payload, self.csrf)
        self.assertEqual(status, 200)
        products = self.request(self.admin, '/api/admin/overview')[1]['products']
        updated = next(p for p in products if p['id'] == self.product_id)
        self.assertEqual(updated['features'], ['One', 'Two'])
        self.assertEqual(updated['technologies'], ['Python'])

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


if __name__ == '__main__':
    unittest.main()
