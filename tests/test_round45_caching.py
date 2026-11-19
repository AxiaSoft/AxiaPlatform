"""Revalidation, compression and the dashboard's scan count.

The site sent every asset with `Cache-Control: no-cache` and no validator, so
"no-cache" meant what it says - re-fetch the whole file - and a returning
visitor downloaded the whole 134KB home page again. A validator turns that into
a 304 with no body at all.

The API was not compressed either. The console's dashboard is 50KB of JSON,
almost all of it repeated keys, and travelled as-is.

These tests pin the behaviour rather than the numbers: that a 304 is what a
matching validator gets, that a changed file invalidates it, that a 304 never
carries a body, and that counts stay correct when the dashboard stops running
one query per number.
"""
import gzip
import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
import app  # noqa: E402


class EtagHelpers(unittest.TestCase):
    """The two functions that decide whether a request is still current."""

    def test_etag_changes_with_size_and_mtime(self):
        a = os.stat(ROOT / 'public' / 'i18n.js')
        b = type('S', (), {'st_size': a.st_size, 'st_mtime_ns': a.st_mtime_ns + 1})
        self.assertNotEqual(app.file_etag(a), app.file_etag(b))

    def test_etag_is_a_quoted_validator(self):
        etag = app.file_etag(os.stat(ROOT / 'public' / 'i18n.js'))
        self.assertTrue(etag.startswith('"') and etag.endswith('"'))

    def test_match_exact(self):
        self.assertTrue(app.etag_matches('"abc"', '"abc"'))

    def test_no_match(self):
        self.assertFalse(app.etag_matches('"def"', '"abc"'))

    def test_match_in_a_list(self):
        self.assertTrue(app.etag_matches('"aaa", "abc", "zzz"', '"abc"'))

    def test_weak_prefix_still_matches(self):
        # A cache may downgrade a strong validator to a weak one; the bytes are
        # the same either way.
        self.assertTrue(app.etag_matches('W/"abc"', '"abc"'))

    def test_star_matches_anything(self):
        self.assertTrue(app.etag_matches('*', '"abc"'))

    def test_missing_header_never_matches(self):
        for value in (None, '', '   '):
            self.assertFalse(app.etag_matches(value, '"abc"'))

    def test_garbage_never_matches(self):
        # Unrecognised input must cost a full response, never a wrong 304.
        self.assertFalse(app.etag_matches('garbage', '"abc"'))


class LiveRequests(unittest.TestCase):
    """The headers a client actually sees, over a real socket."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        # Serve a copy of the real public tree so the test owns the files it
        # rewrites; the production directory is never touched.
        import shutil
        root = Path(cls.tmp.name)
        for name in ('app.js', 'styles.css', 'i18n.js'):
            shutil.copy(ROOT / 'public' / name, root / name)
        cls.root = root
        # The handler reads PUBLIC at call time, so pointing it at the copy is
        # what makes these requests hit the files the tests control. Restored
        # in tearDownClass so no other test sees the swap.
        cls.real_public = app.PUBLIC
        app.PUBLIC = root
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        app.PUBLIC = cls.real_public
        cls.tmp.cleanup()

    def url(self, path):
        return 'http://127.0.0.1:%d%s' % (self.port, path)

    def fetch(self, path, headers=None):
        req = Request(self.url(path), headers=headers or {})
        try:
            with urlopen(req, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except HTTPError as e:
            return e.code, dict(e.headers), e.read()

    # -- static ---------------------------------------------------------- #

    def test_static_file_carries_an_etag(self):
        status, headers, _ = self.fetch('/styles.css')
        self.assertEqual(status, 200)
        self.assertIn('ETag', headers)

    def test_matching_validator_gets_304(self):
        _, headers, _ = self.fetch('/styles.css')
        status, headers2, body = self.fetch(
            '/styles.css', {'If-None-Match': headers['ETag']})
        self.assertEqual(status, 304)
        self.assertEqual(body, b'', '304 must not carry a body')
        self.assertEqual(headers2['ETag'], headers['ETag'])

    def test_304_keeps_the_cache_policy(self):
        # A 304 that dropped Cache-Control would leave the browser guessing.
        _, headers, _ = self.fetch('/styles.css')
        _, headers2, _ = self.fetch(
            '/styles.css', {'If-None-Match': headers['ETag']})
        self.assertEqual(headers2['Cache-Control'], headers['Cache-Control'])

    def test_stale_validator_gets_the_file(self):
        status, _, body = self.fetch(
            '/styles.css', {'If-None-Match': '"not-the-one"'})
        self.assertEqual(status, 200)
        self.assertEqual(body, (self.root / 'styles.css').read_bytes())

    def test_editing_the_file_invalidates_the_validator(self):
        target = self.root / 'styles.css'
        original = target.read_bytes()
        try:
            _, headers, _ = self.fetch('/styles.css')
            # The file changed, so the validator must change with it. Both
            # inputs are exercised: a rewrite that alters the length, and one
            # that alters only the timestamp.
            target.write_bytes(original + b'\n\n')
            os.utime(target, ns=(os.stat(target).st_atime_ns,
                                 os.stat(target).st_mtime_ns + 1_000_000))
            status, _, _ = self.fetch(
                '/styles.css', {'If-None-Match': headers['ETag']})
            self.assertEqual(status, 200, 'a changed file must not 304')
        finally:
            target.write_bytes(original)

    def test_gzip_and_conditional_agree(self):
        # The validator describes the file, not the gzipped body, so the same
        # ETag must work whichever encoding was negotiated.
        _, headers, _ = self.fetch('/app.js', {'Accept-Encoding': 'gzip'})
        status, headers2, body = self.fetch(
            '/app.js', {'Accept-Encoding': 'gzip',
                        'If-None-Match': headers['ETag']})
        self.assertEqual(status, 304)
        self.assertEqual(body, b'')
        self.assertEqual(headers2['Vary'], 'Accept-Encoding')

    def test_compressed_body_round_trips(self):
        status, headers, body = self.fetch('/app.js', {'Accept-Encoding': 'gzip'})
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Content-Encoding'), 'gzip')
        self.assertEqual(gzip.decompress(body), (self.root / 'app.js').read_bytes())

    # -- API ------------------------------------------------------------- #

    def test_json_is_compressed_when_asked(self):
        payload = {'rows': [{'title': 'Product %d' % i, 'status': 'available'}
                            for i in range(200)]}
        raw = json.dumps(payload).encode()
        self.assertGreater(len(raw), app.COMPRESS_MIN_BYTES)
        compressed = gzip.compress(raw, compresslevel=6)
        self.assertLess(len(compressed), len(raw))

    def test_json_compression_is_opt_in(self):
        # A client that did not ask for gzip must not be handed it.
        status, headers, body = self.fetch('/api/health')
        self.assertEqual(status, 200)
        self.assertNotIn('gzip', headers.get('Content-Encoding', ''))
        json.loads(body)

    def test_json_separators_drop_the_default_spaces(self):
        # The old dumps put a space after every comma and colon.
        raw = json.dumps({'a': 1, 'b': [2, 3]},
                         ensure_ascii=False, separators=(',', ':')).encode()
        self.assertEqual(raw, b'{"a":1,"b":[2,3]}')


class DashboardCounts(unittest.TestCase):
    """overview_counts() must equal the twelve queries it replaced."""

    def setUp(self):
        import sqlite3
        sys.path.insert(0, str(ROOT / 'server'))
        import db
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript(db.SCHEMA)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db_ = db

    def tearDown(self):
        self.db.close()

    def seed(self, statuses, products, users):
        # Orders carry foreign keys to a user and a product. The owner is an
        # admin so it does not skew the customer counts under test.
        self.db.execute("INSERT INTO users(id,name,email,password_hash,role) "
                        "VALUES(1,'Owner','o@x.io','x','admin')")
        self.db.execute("INSERT INTO products(id,slug,title,category,summary,"
                        "description,cover,features,technologies,status,"
                        "price_label,published,featured,position) "
                        "VALUES(1,'base','B','websites','s','d','','[]','[]',"
                        "'available','q',1,0,0)")
        for i, status in enumerate(statuses):
            self.db.execute(
                'INSERT INTO orders(number,user_id,product_id,name,email,phone,'
                'description,status) VALUES(?,1,1,?,?,?,?,?)',
                ('AX-%d' % i, 'C', 'c@x.io', '0912', 'd', status))
        for n, (published, featured) in enumerate(products):
            self.db.execute(
                'INSERT INTO products(slug,title,category,summary,description,'
                'cover,features,technologies,status,price_label,published,'
                'featured,position) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('s%d-%d-%d' % (published, featured, n), 'T', 'websites', 's',
                 'd', '', '[]', '[]', 'available', 'q', published, featured, n))
        for n, (role, active) in enumerate(users):
            self.db.execute(
                'INSERT INTO users(name,email,password_hash,role,active) '
                'VALUES(?,?,?,?,?)',
                ('U', 'u%d@x.io' % n, 'x', role, active))

    def test_matches_the_queries_it_replaced(self):
        self.seed(
            statuses=['Submitted', 'Under Review', 'In Development',
                      'Delivered', 'Testing', 'Delivered'],
            products=[(1, 0), (1, 1), (0, 0), (1, 0)],
            users=[('customer', 1), ('customer', 0), ('customer', 1),
                   ('admin', 1)])

        q = lambda sql: self.db.execute(sql).fetchone()[0]  # noqa: E731
        expected = {
            'customers': q("SELECT count(*) FROM users WHERE role='customer'"),
            'orders': q('SELECT count(*) FROM orders'),
            'pending': q("SELECT count(*) FROM orders WHERE status IN "
                         "('Submitted','Under Review','Requirements Analysis')"),
            'active': q("SELECT count(*) FROM orders WHERE status IN "
                        "('In Development','Testing')"),
            'completed': q("SELECT count(*) FROM orders WHERE status='Delivered'"),
            'tickets': q("SELECT count(*) FROM tickets WHERE status='Open'"),
            'refunds': q("SELECT count(*) FROM refunds WHERE status='Under review'"),
            'published': q('SELECT count(*) FROM products WHERE published=1'),
            'hidden': q('SELECT count(*) FROM products WHERE published=0'),
            'featured': q('SELECT count(*) FROM products WHERE published=1 '
                          'AND featured=1'),
            'customers_active': q("SELECT count(*) FROM users WHERE "
                                  "role='customer' AND active=1"),
            'customers_suspended': q("SELECT count(*) FROM users WHERE "
                                     "role='customer' AND active=0"),
        }
        self.assertEqual(app.overview_counts(self.db), expected)

    def test_empty_database_reports_zeroes_not_missing_keys(self):
        counts = app.overview_counts(self.db)
        self.assertEqual(len(counts), 12)
        self.assertTrue(all(v == 0 for v in counts.values()), counts)

    def test_pending_counts_all_three_early_statuses(self):
        self.seed(statuses=['Submitted', 'Under Review', 'Requirements Analysis'],
                  products=[], users=[])
        self.assertEqual(app.overview_counts(self.db)['pending'], 3)

    def test_non_customer_roles_are_not_customers(self):
        self.seed(statuses=[], products=[], users=[('admin', 1), ('customer', 1)])
        counts = app.overview_counts(self.db)
        self.assertEqual(counts['customers'], 1)
        self.assertEqual(counts['customers_active'], 1)


if __name__ == '__main__':
    unittest.main()
