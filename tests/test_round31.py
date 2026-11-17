"""Round 31: the support conversation, from both sides.

The operator's report, in four parts:

    "There is a problem in the support section. Where does the customer see the
     admin's message? Build a place for that. How does the customer know their
     message was sent? How do they know the admin answered? And the admin cannot
     reply to the customer - error Unknown support status."

The last one was the concrete bug and it explains how long the rest had been
broken unnoticed: the reply button failed for anyone reading a Persian console,
so nobody had ever got far enough to notice that the other three did not exist.

    The console built its status <select> without value= attributes, so the
    browser posted the *displayed* text. On a Persian console that text is
    'در حال انجام', and the server only accepted 'In progress'.

Behind it:

    A visitor could open one support request and never say anything again.
    /api/support could only be POSTed to, which creates; there was no route
    to add a message to a ticket the visitor already had. The thread was
    one-way, with the studio able to write and the customer not.

    Nothing recorded that a reply had been read, so there was no way to tell
    "the team answered" from "nothing has happened" - the account page showed
    the same flat paragraph either way.

End-to-end through the real server, with a real session and a real CSRF token.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
import app  # noqa: E402
import db  # noqa: E402

CUSTOMER = {'name': 'Round Thirty One', 'email': 'round31@example.test',
            'password': 'round thirty one password'}
ADMIN_PASSWORD = 'round thirty one admin'


class SupportConversationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.original_db_path = db.DB_PATH
        db.DB_PATH = Path(cls.temp.name) / 'round31.sqlite3'
        db.init()
        conn = db.connect()
        conn.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',
                     ('R31 Admin', 'admin@round31.test', app.hash_password(ADMIN_PASSWORD), 'admin'))
        conn.close()
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
        self.customer = build_opener(HTTPCookieProcessor(CookieJar()))
        self.admin = build_opener(HTTPCookieProcessor(CookieJar()))
        self.csrf = self.login(self.customer, CUSTOMER['email'], CUSTOMER['password'],
                               register=True)
        self.admin_csrf = self.login(self.admin, 'admin@round31.test', ADMIN_PASSWORD)

    # -- helpers ---------------------------------------------------------- #
    def request(self, opener, path, method='GET', payload=None, csrf=None):
        data = None if payload is None else json.dumps(payload).encode()
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
            return error.code, json.loads(body) if body else {}

    def login(self, opener, email, password, register=False):
        if register:
            status, body = self.request(opener, '/api/register', 'POST',
                                        {'name': CUSTOMER['name'], 'email': email,
                                         'password': password})
            self.assertIn(status, (200, 201, 409), body)
        status, body = self.request(opener, '/api/login', 'POST',
                                    {'email': email, 'password': password})
        self.assertEqual(status, 200, body)
        # The token comes from /api/me, not from the login body.
        status, session = self.request(opener, '/api/me')
        self.assertEqual(status, 200, session)
        self.assertIsNotNone(session['user'], session)
        return session['csrf']

    def open_ticket(self, subject='Cannot sign in', message='I cannot sign in to my account at all.'):
        status, body = self.request(self.customer, '/api/support', 'POST',
                                    {'subject': subject, 'message': message}, self.csrf)
        self.assertEqual(status, 201, body)
        status, tickets = self.request(self.customer, '/api/support')
        self.assertEqual(status, 200, tickets)
        match = [t for t in tickets if t['ref'] == body['ref']]
        self.assertTrue(match, tickets)
        return match[0]

    # -- the reported bug -------------------------------------------------- #
    def test_the_admin_can_change_a_status_from_a_persian_console(self):
        """'Unknown support status' - the bug that was reported.

        The console used to send the visible label, and on a Persian console
        that label is not one of the three values the database stores.
        """
        ticket = self.open_ticket()
        for displayed, canonical in (('Open', 'Open'),
                                     ('In progress', 'In progress'),
                                     ('Closed', 'Closed'),
                                     ('در حال انجام', 'In progress'),
                                     ('بسته‌شده', 'Closed'),
                                     ('باز', 'Open')):
            status, body = self.request(self.admin, '/api/admin/tickets/status', 'PUT',
                                        {'id': ticket['id'], 'status': displayed},
                                        self.admin_csrf)
            self.assertEqual(status, 200, f'{displayed!r} was rejected: {body}')
            stored = db.connect().execute('SELECT status FROM tickets WHERE id=?',
                                          (ticket['id'],)).fetchone()['status']
            self.assertEqual(stored, canonical, f'{displayed!r} stored as {stored!r}')

    def test_an_unknown_status_is_still_refused(self):
        ticket = self.open_ticket()
        status, body = self.request(self.admin, '/api/admin/tickets/status', 'PUT',
                                    {'id': ticket['id'], 'status': 'nonsense'},
                                    self.admin_csrf)
        self.assertEqual(status, 400, body)

    def test_the_console_sends_a_canonical_value(self):
        # The <option> must carry value=, or the browser posts the translation.
        # Both copies are checked: admin/ is the source and public/admin/ is what
        # the build ships, and a fix applied to only one of them reaches only
        # half the deployments.
        for relative in ('admin/admin.js', 'public/admin/admin.js'):
            js = (ROOT / relative).read_text(encoding='utf-8')
            start = js.index('ticket-reply" data-id=')
            section = js[start:start + 1100]
            self.assertIn('value="${s}"', section,
                          f'{relative}: the status <option> has no value=, '
                          'so a translated label is posted')
            self.assertIn('esc(T(s))', section,
                          f'{relative}: the label must still be translated')

    # -- where the customer sees the reply -------------------------------- #
    def test_the_customer_sees_the_teams_reply(self):
        ticket = self.open_ticket()
        status, body = self.request(self.admin, '/api/admin/tickets/reply', 'POST',
                                    {'id': ticket['id'], 'message': 'Try resetting it from the sign-in page.'},
                                    self.admin_csrf)
        self.assertEqual(status, 200, body)
        status, tickets = self.request(self.customer, '/api/support')
        self.assertEqual(status, 200, tickets)
        mine = [t for t in tickets if t['id'] == ticket['id']][0]
        replies = [m for m in mine['messages'] if m['from_team']]
        self.assertEqual(len(replies), 1, mine['messages'])
        self.assertEqual(replies[0]['message'], 'Try resetting it from the sign-in page.')

    # -- how the customer knows the team answered ------------------------- #
    def test_a_team_reply_is_counted_as_unread(self):
        ticket = self.open_ticket()
        self.request(self.admin, '/api/admin/tickets/reply', 'POST',
                     {'id': ticket['id'], 'message': 'We are looking into this now.'},
                     self.admin_csrf)
        _, tickets = self.request(self.customer, '/api/support')
        mine = [t for t in tickets if t['id'] == ticket['id']][0]
        self.assertEqual(mine['unread'], 1, mine)

    def test_reading_the_conversation_clears_the_count(self):
        ticket = self.open_ticket()
        self.request(self.admin, '/api/admin/tickets/reply', 'POST',
                     {'id': ticket['id'], 'message': 'A reply that will be read.'},
                     self.admin_csrf)
        status, body = self.request(self.customer, '/api/support/read', 'POST',
                                    {'id': ticket['id']}, self.csrf)
        self.assertEqual(status, 200, body)
        _, tickets = self.request(self.customer, '/api/support')
        mine = [t for t in tickets if t['id'] == ticket['id']][0]
        self.assertEqual(mine['unread'], 0, mine)

    def test_only_the_owner_can_clear_a_conversation(self):
        ticket = self.open_ticket()
        status, body = self.request(self.admin, '/api/support/read', 'POST',
                                    {'id': ticket['id']}, self.admin_csrf)
        self.assertEqual(status, 404, body)

    # -- how the customer answers ----------------------------------------- #
    def test_the_customer_can_reply_inside_their_conversation(self):
        """The missing half of the conversation.

        Before this, POST /api/support only created tickets. A visitor who had
        opened one could not add anything to it - the only way to say more was
        to open a second ticket, which split one conversation into two
        unrelated references.
        """
        ticket = self.open_ticket()
        status, body = self.request(self.customer, f"/api/support/{ticket['id']}/messages",
                                    'POST', {'message': 'It still fails after resetting.'},
                                    self.csrf)
        self.assertEqual(status, 201, body)
        _, tickets = self.request(self.customer, '/api/support')
        mine = [t for t in tickets if t['id'] == ticket['id']][0]
        mine_messages = [m for m in mine['messages'] if not m['from_team']]
        self.assertEqual(len(mine_messages), 1, mine['messages'])
        self.assertEqual(mine_messages[0]['message'], 'It still fails after resetting.')

    def test_the_console_sees_the_customer_reply_as_new(self):
        ticket = self.open_ticket()
        self.request(self.customer, f"/api/support/{ticket['id']}/messages", 'POST',
                     {'message': 'Adding more detail for the team.'}, self.csrf)
        _, tickets = self.request(self.admin, '/api/support')
        mine = [t for t in tickets if t['id'] == ticket['id']][0]
        self.assertGreaterEqual(mine['unread_for_team'], 1, mine)

    def test_nobody_can_write_into_someone_elses_conversation(self):
        ticket = self.open_ticket()
        other = build_opener(HTTPCookieProcessor(CookieJar()))
        self.login(other, 'other@round31.test', 'another round thirty one password',
                   register=True)
        status, tickets = self.request(other, '/api/support')
        self.assertEqual(status, 200)
        self.assertEqual(tickets, [], 'a stranger must not see this conversation')
        # And the id itself must not be writable just because it is guessable.
        other_csrf = self.request(other, '/api/me')[1]['csrf']
        status, body = self.request(other, '/api/support', 'POST',
                                    {'subject': 'Mine', 'message': 'A different customer here.'},
                                    other_csrf)
        self.assertEqual(status, 201, body)
        status, body = self.request(other, f"/api/support/{ticket['id']}/messages", 'POST',
                                    {'message': 'Trying to write into another conversation.'},
                                    other_csrf)
        self.assertEqual(status, 404, body)

    def test_writing_again_reopens_a_closed_conversation(self):
        ticket = self.open_ticket()
        self.request(self.admin, '/api/admin/tickets/status', 'PUT',
                     {'id': ticket['id'], 'status': 'Closed'}, self.admin_csrf)
        status, body = self.request(self.customer, f"/api/support/{ticket['id']}/messages",
                                    'POST', {'message': 'One more thing, sorry.'}, self.csrf)
        self.assertEqual(status, 201, body)
        _, tickets = self.request(self.customer, '/api/support')
        mine = [t for t in tickets if t['id'] == ticket['id']][0]
        self.assertEqual(mine['status'], 'Open', mine)

    def test_an_empty_reply_is_refused(self):
        ticket = self.open_ticket()
        status, body = self.request(self.customer, f"/api/support/{ticket['id']}/messages",
                                    'POST', {'message': ' '}, self.csrf)
        self.assertEqual(status, 400, body)

    def test_a_reply_needs_the_session(self):
        ticket = self.open_ticket()
        anonymous = build_opener(HTTPCookieProcessor(CookieJar()))
        status, body = self.request(anonymous, f"/api/support/{ticket['id']}/messages",
                                    'POST', {'message': 'No session here.'})
        self.assertIn(status, (401, 403), body)


class SupportInterfaceTests(unittest.TestCase):
    """The page the customer uses, checked at the source level."""

    def setUp(self):
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')

    def test_the_account_page_has_a_reply_box(self):
        self.assertIn('ticket-reply-form', self.app_js)
        self.assertIn('/messages', self.app_js)

    def test_the_account_page_shows_who_wrote_each_message(self):
        self.assertIn('from_team', self.app_js)

    def test_the_account_page_shows_an_unread_count(self):
        self.assertIn('t.unread', self.app_js)

    def test_the_account_page_marks_the_conversation_read(self):
        self.assertIn('/api/support/read', self.app_js)

    def test_the_confirmation_names_the_reference_and_where_to_reply(self):
        # The old message said "created, the team will follow up" and vanished.
        self.assertIn('Open my conversations', self.app_js)

    def test_the_new_strings_are_in_the_dictionary(self):
        i18n = (ROOT / 'public' / 'i18n.js').read_text(encoding='utf-8')
        for phrase in ("'Send reply'", "'Write a reply to the team…'",
                       "'AXIASOFT support'", "'This conversation is closed. Writing again reopens it.'"):
            self.assertIn(phrase, i18n)


class SupportStyleTests(unittest.TestCase):
    def test_the_thread_has_styles(self):
        css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')
        for selector in ('.ticket-thread', '.ticket-msg', '.ticket-msg.team',
                         '.ticket-reply-form'):
            self.assertIn(selector, css)


if __name__ == '__main__':
    unittest.main()
