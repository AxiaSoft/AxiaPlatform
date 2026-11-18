"""Round 33: a messages entry in the customer panel, a full-page messenger,
ticket priority, and one customer in full for the console.

Four asks in one message:

    "Put a Messages entry in the customer panel.
     Make the messenger a full page, conversations shown as a column, and
     clicking one opens that chat.
     New chats should take a subject and a ticket priority.
     Show the customer's details in the admin panel, and let the admin control
     everything about that user - orders, payments, everything."

The third one was half-built before this round: `tickets.priority` existed with
a 'Normal' default, but no route ever wrote another value and no screen showed
one, so it was a column nobody could reach.

The fourth is the one to be careful with. "Control everything" cannot mean
seeing a password hash or moving money that no provider is connected to. The
profile shows everything the database actually holds about an account, offers
the controls the server already enforces, and says in the page itself where its
power stops.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))


class PriorityTests(unittest.TestCase):
    """The priority column had a default and no writer."""

    def setUp(self):
        import app
        self.app = app

    def test_english_values_survive(self):
        for value in ('Low', 'Normal', 'High', 'Urgent'):
            self.assertEqual(self.app.ticket_priority(value), value)

    def test_persian_values_are_understood(self):
        # A Persian console posts what the operator sees, which is the lesson
        # from the status bug in round 31.
        self.assertEqual(self.app.ticket_priority('فوری'), 'Urgent')
        self.assertEqual(self.app.ticket_priority('بالا'), 'High')
        self.assertEqual(self.app.ticket_priority('کم'), 'Low')
        self.assertEqual(self.app.ticket_priority('معمولی'), 'Normal')

    def test_case_and_padding_do_not_matter(self):
        self.assertEqual(self.app.ticket_priority('  high '), 'High')
        self.assertEqual(self.app.ticket_priority('URGENT'), 'Urgent')

    def test_an_unknown_priority_degrades_to_normal(self):
        # Not a 400: a typo must not cost the customer their message.
        self.assertEqual(self.app.ticket_priority('whenever'), 'Normal')
        self.assertEqual(self.app.ticket_priority(None), 'Normal')
        self.assertEqual(self.app.ticket_priority(''), 'Normal')

    def test_the_create_route_writes_the_priority(self):
        source = (ROOT / 'server' / 'app.py').read_text(encoding='utf-8')
        start = source.index("if p == '/api/support':\n            if method != 'POST'")
        block = source[start:start + 1400]
        self.assertIn('ticket_priority(d.get(', block)
        self.assertIn('INSERT INTO tickets(ref,user_id,email,subject,message,priority)', block)

    def test_the_create_route_reports_what_it_stored(self):
        source = (ROOT / 'server' / 'app.py').read_text(encoding='utf-8')
        start = source.index("if p == '/api/support':\n            if method != 'POST'")
        self.assertIn("'priority': priority", source[start:start + 1400])


class MessengerLayoutTests(unittest.TestCase):
    """The messenger is a page per view now, and the list is a column."""

    def setUp(self):
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')

    def test_each_view_is_a_page_of_its_own(self):
        # #/messages, #/messages/new and #/messages/<id> are three pages, not
        # two panes sharing one frame.
        for marker in ('class="container msg-page"', 'msg-page msg-page-chat'):
            self.assertIn(marker, self.app_js)

    def test_the_conversations_are_a_column_of_rows(self):
        self.assertIn('class="msg-column"', self.app_js)
        self.assertIn('.msg-column{display:flex;flex-direction:column', self.css)
        # A row is a whole line, not a card in a wrapping grid.
        self.assertNotIn('.msg-app', self.css)

    def test_a_row_opens_that_conversation(self):
        self.assertIn('data-msg-open', self.app_js)
        self.assertIn("go('/messages/' + a.dataset.msgOpen)", self.app_js)

    def test_an_open_conversation_leaves_the_list_behind(self):
        # The deep link has to render the thread and nothing else, so a shared
        # link does not land on a page the reader has to navigate.
        block = self.app_js[self.app_js.index('if (open) {'):]
        block = block[:block.index('} else {')]
        self.assertIn('msgThread(open)', block)
        self.assertNotIn('msgList(', block)

    def test_every_page_can_get_back(self):
        self.assertIn('msg-back', self.app_js)
        self.assertIn("href=\"#/messages\"", self.app_js)


class PanelEntryTests(unittest.TestCase):
    def setUp(self):
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')

    def test_the_panel_leads_to_messages(self):
        # The ask was an entry in the customer panel, not only in the header.
        self.assertIn('class="card stat-card stat-link" href="#/messages"', self.app_js)

    def test_the_entry_carries_the_unread_count(self):
        self.assertIn('unreadTotal', self.app_js)
        self.assertIn('tickets.reduce((a,t)=>a+(t.unread||0),0)', self.app_js)


class CustomerProfileTests(unittest.TestCase):
    """One customer in full, with the controls the server actually has."""

    def setUp(self):
        self.source = (ROOT / 'server' / 'app.py').read_text(encoding='utf-8')
        self.admin_js = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')

    def test_the_endpoint_answers_one_customer(self):
        self.assertIn("p == '/api/admin/customers/detail'", self.source)

    def test_it_is_not_an_exact_match_route_that_swallows_the_detail(self):
        # '/api/admin/customers' is matched with ==, so the detail route is not
        # hidden behind it. Stated as a test because a change to that == would
        # break this in a way nothing else would notice.
        self.assertIn("if p == '/api/admin/customers':", self.source)
        self.assertIn("if p == '/api/admin/customers/detail':", self.source)

    def test_a_credential_never_reaches_the_browser(self):
        start = self.source.index("p == '/api/admin/customers/detail'")
        block = self.source[start:start + 4200]
        self.assertIn("for secret in ('password_hash', 'token', 'reset_token')", block)
        self.assertIn('profile.pop(secret, None)', block)

    def test_an_unknown_id_is_a_404(self):
        start = self.source.index("p == '/api/admin/customers/detail'")
        self.assertIn("self._send_json({'error': 'No such customer'}, 404)",
                      self.source[start:start + 4200])

    def test_the_profile_carries_the_whole_account(self):
        start = self.source.index("p == '/api/admin/customers/detail'")
        block = self.source[start:start + 4200]
        for part in ("'orders'", "'refunds'", "'tickets'", "'events'"):
            self.assertIn(part, block, f'{part} is missing from the profile payload')

    def test_the_page_says_where_its_power_stops(self):
        # A screen that looks like it moves money must not imply that it does.
        self.assertIn('No money is transferred', self.admin_js)
        self.assertIn('Passwords and card details are never shown, and nothing here moves money.',
                      self.admin_js)

    def test_the_directory_opens_a_profile(self):
        self.assertIn('data-act="customer-open"', self.admin_js)
        self.assertIn("if(act==='customer-open'){openCustomer(b.dataset.id);return}", self.admin_js)

    def test_the_profile_re_issues_order_status(self):
        """Changing a status on the profile still writes through the API.

        The control is a picker rather than a <select> - a native select opens
        the operating system's menu - so the callback carries the id in the
        picker's own data-id and posts the same endpoint.
        """
        self.assertIn("api('/api/admin/orders/status'", self.admin_js)
        self.assertIn('pickerCustomerOrderStatus', self.admin_js)
        self.assertIn("dataId:o.id", self.admin_js)

    def test_the_profile_re_issues_refund_decisions(self):
        self.assertIn("api('/api/admin/refunds/decision'", self.admin_js)
        self.assertIn('customerRefund', self.admin_js)

    def test_the_profile_can_suspend_the_account(self):
        self.assertIn('data-act="customer-status"', self.admin_js)


class ConsolePriorityTests(unittest.TestCase):
    def setUp(self):
        self.admin_js = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')
        self.i18n = (ROOT / 'public' / 'i18n.js').read_text(encoding='utf-8')

    def test_the_inbox_shows_a_priority_column(self):
        self.assertIn('<th>Priority</th>', self.admin_js)

    def test_the_ticket_modal_shows_the_priority(self):
        self.assertIn('<small>Priority</small>', self.admin_js)

    def test_every_priority_has_a_persian_name(self):
        for key, value in (('Low', 'کم'), ('Normal', 'معمولی'), ('High', 'بالا'), ('Urgent', 'فوری')):
            self.assertIn(f"'{key}':'{value}'", self.i18n)


class TranslationHygieneTests(unittest.TestCase):
    def setUp(self):
        self.i18n = (ROOT / 'public' / 'i18n.js').read_text(encoding='utf-8')

    def test_the_messenger_and_profile_strings_are_translated(self):
        for phrase in ("'Priority'", "'Conversations'", "'Open conversations'",
                       "'Customer ID'", "'Suspend account'", "'Reactivate account'",
                       "'Open profile'", "'Project requests'", "'Activity'"):
            self.assertIn(phrase, self.i18n, f'{phrase} is missing from the dictionary')

    def test_every_string_the_messenger_translates_has_a_persian_entry(self):
        # AXIA_T returns its input when the dictionary has no entry, so a
        # missing key is invisible in the code and English on the page. This
        # caught "Send message" shipping untranslated.
        app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        start = app_js.index('/* ---------------------------------------------------------- the messenger')
        block = app_js[start:]
        missing = sorted({m.group(1) for m in re.finditer(r"AXIA_T\('((?:[^'\\]|\\.)*)'\)", block)
                          if f"'{m.group(1)}':" not in self.i18n and f'"{m.group(1)}":' not in self.i18n})
        self.assertEqual(missing, [], 'these stay English in a Persian page')

    def test_every_string_the_customer_profile_translates_has_a_persian_entry(self):
        admin_js = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')
        start = admin_js.index('async function openCustomer(')
        block = admin_js[start:admin_js.index('function customersHTML()')]
        missing = sorted({m.group(1) for m in re.finditer(r"T\('((?:[^'\\]|\\.)*)'\)", block)
                          if f"'{m.group(1)}':" not in self.i18n and f'"{m.group(1)}":' not in self.i18n})
        self.assertEqual(missing, [], 'these stay English in a Persian console')

    def test_no_new_key_is_defined_twice_with_different_words(self):
        # A second entry for a key silently wins over the first, so the earlier
        # text becomes dead without anyone noticing.
        start = self.i18n.index('const fa={') + len('const fa={')
        end = self.i18n.index('\n};', start)
        seen = {}
        for key, value in re.findall(r"'((?:[^'\\]|\\.)*)'\s*:\s*'((?:[^'\\]|\\.)*)'", self.i18n[start:end]):
            seen.setdefault(key, []).append(value)
        mine = {'Priority', 'Low', 'Normal', 'High', 'Urgent', 'Customer ID', 'Suspend account',
                'Reactivate account', 'Open profile', 'Open conversations', 'Requests',
                'Order status updated.', 'Refund decision recorded.', 'A decision is recorded only. No money is transferred.'}
        for key in mine & set(seen):
            self.assertEqual(len(seen[key]), 1, f'{key} is defined {len(seen[key])} times')


if __name__ == '__main__':
    unittest.main()
