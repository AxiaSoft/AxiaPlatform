import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import db, app

class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); db.DB_PATH=Path(cls.tmp.name)/'test.sqlite3'; db.init()
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def test_password_hash_is_salted_and_verifiable(self):
        a=app.hash_password('correct horse battery staple'); b=app.hash_password('correct horse battery staple')
        self.assertNotEqual(a,b); self.assertTrue(app.verify_password('correct horse battery staple',a)); self.assertFalse(app.verify_password('wrong',a)); self.assertNotIn('correct horse',a)
    def test_catalog_starts_empty_and_stores_products(self):
        # The shipped catalog is intentionally empty; products are created from
        # the admin console. This test therefore seeds none and inserts its own.
        conn=db.connect(); self.assertEqual(len(conn.execute('SELECT * FROM products').fetchall()),0)
        conn.execute('INSERT INTO products(slug,title,category,summary,description,features,technologies) VALUES(?,?,?,?,?,?,?)',
                     ('test-product','Test Product','Websites','Summary','Description','["One","Two"]','["Python"]'))
        products=conn.execute('SELECT * FROM products').fetchall(); conn.close()
        self.assertEqual(len(products),1)
        website=products[0]
        self.assertTrue(website['slug']); self.assertGreaterEqual(len(__import__('json').loads(website['features'])),2)
        self.assertEqual(website['github_url'],'')  # default is empty, not NULL

    def test_github_url_column_and_migration(self):
        # A database created before this column existed must be upgraded in place.
        conn=db.connect()
        self.assertIn('github_url',{r[1] for r in conn.execute('PRAGMA table_info(products)')})
        conn.close()
        import sqlite3, tempfile
        from pathlib import Path as _P
        legacy=_P(tempfile.mkdtemp())/'legacy.sqlite3'
        old=sqlite3.connect(str(legacy))
        old.execute('CREATE TABLE products(id INTEGER PRIMARY KEY, slug TEXT, title TEXT, category TEXT, summary TEXT, description TEXT, cover TEXT, features TEXT, technologies TEXT, status TEXT, price_label TEXT, published INTEGER)')
        old.commit(); old.close()
        previous=db.DB_PATH; db.DB_PATH=legacy
        try:
            db.init()
            conn=db.connect()
            self.assertIn('github_url',{r[1] for r in conn.execute('PRAGMA table_info(products)')})
            conn.close()
        finally:
            db.DB_PATH=previous
    def test_roles_constrained_and_emails_unique(self):
        conn=db.connect(); pw=app.hash_password('a sufficiently long test password')
        conn.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',('One','one@example.test',pw,'customer'))
        with self.assertRaises(Exception): conn.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',('Duplicate','one@example.test',pw,'customer'))
        with self.assertRaises(Exception): conn.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',('Invalid','bad@example.test',pw,'superadmin'))
        conn.close()
    def test_private_session_token_stored_as_hash(self):
        token='random-session-token'; self.assertNotEqual(app.token_hash(token),token); self.assertEqual(len(app.token_hash(token)),64)
    def test_order_status_history_table_exists(self):
        conn=db.connect(); tables={r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}; conn.close()
        self.assertTrue({'orders','order_history','audit_logs','ticket_messages','refunds'}.issubset(tables))

if __name__=='__main__': unittest.main()
