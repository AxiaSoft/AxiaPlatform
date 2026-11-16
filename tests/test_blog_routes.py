"""The blog over real HTTP: a published post resolves, a missing one does not.

These run a real server against a temporary database, because the bugs they pin
were about status codes and URLs — the parts a string assertion cannot check.
"""
import json
import re
import sys
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import app
import db

LONG_BODY = ('This is a paragraph of article text long enough to survive the '
             'schema, with a second sentence so the reading time is real.')


class BlogRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_db_path = db.DB_PATH
        cls.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(cls.temp.name) / 'blog-routes.sqlite3'
        db.init()
        conn = db.connect()
        conn.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',
                     ('Blog Admin', 'blog@example.test', app.hash_password('blog test password'), 'admin'))
        cls.published_id = conn.execute(
            'INSERT INTO articles(slug,title,summary,body,status,language,published_at) '
            "VALUES(?,?,?,?,'published','fa',CURRENT_TIMESTAMP)",
            ('a-live-post', 'A live post', 'Summary.', LONG_BODY)).lastrowid
        cls.draft_id = conn.execute(
            'INSERT INTO articles(slug,title,summary,body,status,language) '
            "VALUES(?,?,?,?,'draft','fa')",
            ('a-draft', 'A draft', 'Summary.', LONG_BODY)).lastrowid
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

    def get(self, path):
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        try:
            with opener.open(Request(self.base + path), timeout=10) as response:
                return response.status, response.read().decode('utf-8', 'replace')
        except HTTPError as exc:
            return exc.code, exc.read().decode('utf-8', 'replace')

    def test_the_published_post_resolves(self):
        status, body = self.get('/blog/a-live-post/')
        self.assertEqual(status, 200)
        self.assertIn('A live post', body)

    def test_the_published_post_resolves_without_a_trailing_slash(self):
        # Redirected or served; either is fine, but not a 404.
        status, _ = self.get('/blog/a-live-post')
        self.assertIn(status, (200, 301, 302, 308))

    def test_a_missing_post_is_404_not_200(self):
        # The regression: 404.html handed to serve_static() came back as 200.
        for path in ('/blog/no-such-post/', '/blog/no-such-post',
                     '/en/blog/no-such-post/'):
            status, _ = self.get(path)
            self.assertEqual(status, 404, f'{path} answered {status}')

    def test_a_draft_is_404(self):
        status, _ = self.get('/blog/a-draft/')
        self.assertEqual(status, 404, 'a draft must not be readable by URL')

    def test_the_index_lists_the_published_post_only(self):
        status, body = self.get('/blog/')
        self.assertEqual(status, 200)
        self.assertIn('a-live-post', body)
        self.assertNotIn('a-draft', body)

    def test_the_english_mirror_does_not_404_the_slug(self):
        # Every slug gets a page in the English tree so the language switch does
        # not dead-end, even when there is no stored translation.
        status, _ = self.get('/en/blog/a-live-post/')
        self.assertEqual(status, 200)

    def test_a_missing_feed_entry_is_not_invented(self):
        status, body = self.get('/blog/feed.xml')
        self.assertEqual(status, 200)
        self.assertIn('a-live-post', body)
        self.assertNotIn('a-draft', body)

    def test_the_sitemap_lists_the_published_post_only(self):
        status, body = self.get('/sitemap.xml')
        self.assertEqual(status, 200)
        self.assertIn('a-live-post', body)
        self.assertNotIn('a-draft', body)


class BlogThemeTests(unittest.TestCase):
    """The blog must open on the same theme as the storefront.

    Before this, blog pages resolved the theme from localStorage and the OS
    only — the administrator's default never reached them, so a site set to
    open in light mode still showed every article on a dark page. These tests
    read what the server actually sends, and then run that script to see which
    theme it lands on.
    """

    @classmethod
    def setUpClass(cls):
        cls.original_db_path = db.DB_PATH
        cls.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(cls.temp.name) / 'blog-theme.sqlite3'
        db.init()
        conn = db.connect()
        conn.execute(
            'INSERT INTO articles(slug,title,summary,body,status,language,published_at) '
            "VALUES(?,?,?,?,'published','fa',CURRENT_TIMESTAMP)",
            ('themed-post', 'A themed post', 'Summary.', LONG_BODY))
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

    def get(self, path):
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        try:
            with opener.open(Request(self.base + path), timeout=10) as response:
                return response.status, response.read().decode('utf-8', 'replace')
        except HTTPError as exc:
            return exc.code, exc.read().decode('utf-8', 'replace')

    def set_theme(self, value):
        conn = db.connect()
        try:
            db.save_settings(conn, {'default_theme': value})
        finally:
            conn.close()

    def fallback_in(self, path):
        """The administrator's default as the page's script receives it."""
        status, body = self.get(path)
        self.assertEqual(status, 200)
        match = re.search(r'var fallback = ("(?:[^"\\]|\\.)*");', body)
        self.assertIsNotNone(match, 'the theme script must ship a fallback')
        return json.loads(match.group(1))

    def test_the_administrator_default_reaches_the_index(self):
        self.set_theme('light')
        self.assertEqual(self.fallback_in('/blog/'), 'light')

    def test_the_administrator_default_reaches_an_article(self):
        self.set_theme('light')
        self.assertEqual(self.fallback_in('/blog/themed-post/'), 'light')

    def test_the_administrator_default_reaches_the_english_tree(self):
        self.set_theme('light')
        self.assertEqual(self.fallback_in('/en/blog/themed-post/'), 'light')

    def test_system_is_passed_through_not_resolved_on_the_server(self):
        # 'system' must survive as a value: the server cannot know the visitor's
        # OS, and hard-coding either theme here would be the same bug again.
        self.set_theme('system')
        self.assertEqual(self.fallback_in('/blog/'), 'system')

    def test_a_fresh_install_sends_the_documented_default(self):
        conn = db.connect()
        try:
            db.save_settings(conn, {'default_theme': 'dark'})
        finally:
            conn.close()
        self.assertEqual(self.fallback_in('/blog/'), 'dark')

    def test_the_theme_script_prefers_a_saved_choice(self):
        # A toggle on the storefront writes axia-theme; the blog must honour it
        # rather than overwriting the visitor's choice with the admin default.
        status, body = self.get('/blog/')
        self.assertEqual(status, 200)
        script = re.search(r'var fallback = .*?document\.documentElement\.dataset\.theme = t;',
                           body, re.S)
        self.assertIsNotNone(script, 'the resolver must read localStorage first')
        text = script.group(0)
        self.assertLess(text.index("getItem('axia-theme')"), text.index('fallback ==='))
