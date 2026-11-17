"""Round 32: the messenger, a page of its own for talking to the team.

The ask:

    "Build a chat page so the customer can talk to the admin easily and open a
     ticket - a whole page, shaped like a messenger."

Round 31 made the conversation two-way and gave it read state, but it lived as
a card on the account page: one flat block per request, found by scrolling past
orders. It worked and it did not read as a conversation, and a visitor with a
question had to know to look there.

This round draws the same data as a messenger:

    conversations on one side, the open thread on the other, the box to write
    in at the bottom of the open conversation, and a count wherever a reply is
    waiting.

No new endpoints: /api/support already carries every ticket with its messages,
its read state and both unread counts. The work here is a route, a view, and
the states that make it feel alive - a composer that grows, a send that says
what it is doing, a poll that brings a reply in without a reload.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MessengerRouteTests(unittest.TestCase):
    def setUp(self):
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')

    def test_the_route_exists_and_survives_a_deep_link(self):
        # '#/messages/12' has to open conversation 12, because that is the link
        # the console and a notification would carry.
        self.assertIn("path==='/messages'||path.startsWith('/messages/')", self.app_js)
        self.assertIn("messenger(path.split('/')[2]||null)", self.app_js)

    def test_a_closed_tab_does_not_keep_polling(self):
        # The poll is the one thing here that costs a request on a timer, so it
        # has to stop when nobody is looking.
        self.assertIn('if (document.hidden) return', self.app_js)
        self.assertIn("if (!location.hash.startsWith('#/messages'))", self.app_js)

    def test_a_stale_render_cannot_paint_over_a_newer_one(self):
        # Clicking conversation A then B used to leave A on screen when A's
        # request finished last.
        self.assertIn('const gen = ++msgGen', self.app_js)
        self.assertIn('if (gen !== msgGen) return', self.app_js)

    def test_a_failed_load_is_not_shown_as_an_empty_inbox(self):
        # "Nothing here yet" and "we could not reach the server" are different
        # facts, and telling a customer with open tickets the first one is a lie.
        self.assertIn('loadFailed', self.app_js)
        self.assertIn('Could not load your conversations', self.app_js)


class MessengerThreadTests(unittest.TestCase):
    def setUp(self):
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')

    def test_a_message_knows_which_side_wrote_it(self):
        self.assertIn("msgTickets = Array.isArray(tickets)", self.app_js)
        self.assertIn('m.from_team', self.app_js)
        self.assertIn('msg-row.mine', (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8'))

    def test_the_team_bubble_says_who_it_is_from(self):
        self.assertIn("AXIA_T('AXIASOFT support')", self.app_js)

    def test_the_thread_is_scrolled_to_the_newest_message(self):
        self.assertIn('scroll.scrollTop = scroll.scrollHeight', self.app_js)

    def test_days_are_separated(self):
        self.assertIn('function msgDay(', self.app_js)
        self.assertIn('msg-day', self.app_js)
        self.assertIn("AXIA_T('Today')", self.app_js)

    def test_the_question_is_in_the_thread_with_its_answers(self):
        # A ticket stores its opening message in tickets.message and only the
        # replies in ticket_messages. Drawing the replies alone showed answers
        # to a question that was not on the page.
        self.assertIn('function msgWithOpening(', self.app_js)
        self.assertIn('msgWithOpening(t, msgs)', self.app_js)

    def test_the_poll_and_the_first_paint_agree_on_the_thread(self):
        # Two places draw the thread; if only one adds the opening message, the
        # question disappears the first time a reply arrives.
        self.assertEqual(self.app_js.count('msgWithOpening('), 3,
                         'both renders must build the thread through msgWithOpening')

    def test_the_avatar_is_the_person_not_the_subject(self):
        self.assertIn('msgInitials(me && me.name)', self.app_js)
        self.assertNotIn('msgInitials(t.from_team ? t.subject', self.app_js)

    def test_the_reply_box_survives_a_redraw(self):
        # The poll redraws the thread when a reply arrives; a draft must not be
        # thrown away because the other side answered.
        self.assertIn('msgDraft', self.app_js)
        self.assertIn('box.value = msgDraft[form.dataset.ticket]', self.app_js)

    def test_enter_sends_and_shift_enter_does_not(self):
        self.assertIn('!e.shiftKey', self.app_js)
        self.assertIn('!e.isComposing', self.app_js)

    def test_the_textarea_grows_with_the_message(self):
        self.assertIn('function grow', self.app_js.replace('const grow = ', 'function grow'))
        self.assertIn("box.style.height = 'auto'", self.app_js)


class MessengerComposeTests(unittest.TestCase):
    def setUp(self):
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')

    def test_a_new_conversation_is_written_in_the_same_pane(self):
        # Not a modal: the first message of a conversation is written in the
        # place every later one is written.
        self.assertIn('function msgCompose()', self.app_js)
        self.assertIn("id=\"msg-new-form\"", self.app_js)

    def test_sending_a_new_conversation_lands_on_its_thread(self):
        # A ref in a toast is not confirmation; the conversation you started is.
        self.assertIn("go('/messages/' + t.id)", self.app_js)

    def test_the_reply_is_sent_to_the_message_route(self):
        self.assertIn("'/api/support/' + form.dataset.ticket + '/messages'", self.app_js)


class MessengerSignalTests(unittest.TestCase):
    def setUp(self):
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.i18n = (ROOT / 'public' / 'i18n.js').read_text(encoding='utf-8')

    def test_the_header_carries_an_unread_count(self):
        self.assertIn('function unreadChrome()', self.app_js)
        self.assertIn('nav-count', self.app_js)

    def test_the_header_entry_is_hidden_and_never_removed(self):
        # refresh() runs before anyone signs in. Removing the node there meant
        # signing in afterwards had nothing to draw into.
        self.assertIn('slot.hidden=true', self.app_js.replace(' ', ''))
        self.assertNotIn('slot.remove()', self.app_js)

    def test_the_count_clears_when_the_conversation_is_read(self):
        self.assertIn("api('/api/support/read'", self.app_js)
        self.assertIn('unreadChrome();', self.app_js)

    def test_opening_a_conversation_marks_it_read(self):
        self.assertIn('if (open && open.unread)', self.app_js)

    def test_the_messenger_strings_are_in_the_dictionary(self):
        for phrase in ("'Conversations'", "'No conversation open'", "'New conversation'",
                       "'All conversations'", "'Write a message…'", "'Today'", "'Yesterday'",
                       "'Nothing here yet. Start a conversation and it will appear here.'",
                       "'Could not load your conversations. Check the connection and try again.'"):
            self.assertIn(phrase, self.i18n, f'{phrase} is missing from the dictionary')

    def test_no_dictionary_key_is_defined_twice_with_different_words(self):
        # A second entry for the same key silently wins over the first, which
        # makes the earlier one dead text nobody notices.
        start = self.i18n.index('const fa={') + len('const fa={')
        end = self.i18n.index('\n};', start)
        block = self.i18n[start:end]
        seen = {}
        for key, value in re.findall(r"'((?:[^'\\]|\\.)*)'\s*:\s*'((?:[^'\\]|\\.)*)'", block):
            seen.setdefault(key, []).append(value)
        # 'Reference' predates this round and is a separate cleanup; everything
        # the messenger added has to be unambiguous.
        mine = {'Conversations', 'No conversation open', 'New conversation',
                'All conversations', 'Write a message…', 'Today', 'Yesterday',
                'Messages', 'Nothing here yet. Start a conversation and it will appear here.'}
        for key in mine & set(seen):
            self.assertEqual(len(seen[key]), 1,
                             f'{key} is defined {len(seen[key])} times in the dictionary')


class MessengerStyleTests(unittest.TestCase):
    def setUp(self):
        self.css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')

    def test_the_two_pane_layout_collapses_on_a_phone(self):
        block = self.css[self.css.index('@media(max-width:820px){'):]
        self.assertIn('.msg-app.thread-open .msg-side{display:none}', block)
        self.assertIn('.msg-app:not(.thread-open) .msg-pane{display:none}', block)

    def test_the_bubbles_have_both_sides(self):
        for selector in ('.msg-bubble', '.msg-row.mine .msg-bubble', '.msg-meta'):
            self.assertIn(selector, self.css)

    def test_the_unread_count_has_a_style(self):
        for selector in ('.msg-badge', '.nav-count'):
            self.assertIn(selector, self.css)

    def test_the_header_entry_survives_the_smallest_screen(self):
        # The header has the least room on a phone and the most need for this.
        self.assertNotIn('@media(max-width:640px){.nav-messages{display:none}}', self.css)


class MessengerMarkupTests(unittest.TestCase):
    """The header link is drawn by the page, so it has to exist in the shell."""

    def setUp(self):
        self.html = (ROOT / 'public' / 'index.html').read_text(encoding='utf-8')

    def test_the_shell_has_the_slot_the_script_fills(self):
        self.assertIn('id="messagesButton"', self.html)

    def test_it_starts_hidden_because_the_visitor_may_not_be_signed_in(self):
        anchor = self.html[self.html.index('id="messagesButton"'):]
        self.assertIn('hidden', anchor[:120])


if __name__ == '__main__':
    unittest.main()
