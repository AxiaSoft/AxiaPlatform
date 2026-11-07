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
    def test_catalog_seeded_and_structured(self):
        conn=db.connect(); products=conn.execute('SELECT * FROM products').fetchall(); conn.close()
        self.assertGreaterEqual(len(products),6)
        website=next(p for p in products if p['category']=='Websites')
        self.assertTrue(website['slug']); self.assertTrue(__import__('json').loads(website['features']))
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
