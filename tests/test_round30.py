"""Round 30: answer in the language the visitor wrote in, and converse.

The operator's report, in his words:

    "the chatbot speaks English; make it answer in English when I speak English
     and in Persian when I speak Persian. Right now it only speaks English when
     I speak Persian to it."
    "I want it to answer like an AI. I'll give it an API - put it in .env."

Two faults sat behind that, and neither was the missing key:

1. The reply language was the *site's*, deliberately: `answer()` took the
   interface language from `document.documentElement.lang` and the system
   prompt said "Do not mirror the question". So a Persian question on the
   English build got an English answer by design, and a Persian question on a
   Persian build still got English when the English copy scored higher.

2. The prompt asked for retrieval recitation: "at most four sentences", "no
   bullet lists", "if a fact is not in PUBLISHED text, say so". A greeting came
   back as "Hi, I'm Xiona - this site's own assistant. Ask me about products...",
   which is the panel's text, not a reply to what was said.

Nothing here makes a network call: the provider is replaced with a stub.
"""
import json
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
import agent  # noqa: E402
import xiona_engine  # noqa: E402


class QuestionLanguageTests(unittest.TestCase):
    """The question decides the reply language, not the site."""

    def setUp(self):
        agent._LAST_CALL.update(ok=None, error=None, at=None)
        self.addCleanup(agent._LAST_CALL.update, ok=None, error=None, at=None)

    def test_a_persian_question_is_answered_in_persian(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('AXIA_AGENT_KEY', None)
            reply = agent.answer('محصولاتتون چیه؟')
        self.assertEqual(reply['language'], 'fa')

    def test_an_english_question_is_answered_in_english(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('AXIA_AGENT_KEY', None)
            reply = agent.answer('what do you build?')
        self.assertEqual(reply['language'], 'en')

    def test_an_explicit_language_still_wins(self):
        # A caller with better information - a script, a test - is obeyed.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('AXIA_AGENT_KEY', None)
            reply = agent.answer('محصولاتتون چیه؟', language='en')
        self.assertEqual(reply['language'], 'en')

    def test_the_prompt_names_the_language_of_the_question(self):
        body = (ROOT / 'server' / 'agent.py').read_text(encoding='utf-8')
        prompt = body[body.index('SYSTEM_PROMPT = ('):body.index('LANGUAGE_NAMES = ')]
        self.assertIn('the language the visitor wrote in', prompt)
        self.assertNotIn('Do not mirror the question', prompt)
        self.assertIn('translate anything you take from it', prompt)

    def test_the_browser_does_not_send_its_own_language(self):
        js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        start = js.index("fetch('/api/agent'")
        self.assertNotIn('language:', js[start:start + 260])

    def test_the_route_still_accepts_a_language(self):
        # The parameter has to keep working for the admin preview and the tests
        # even though the browser no longer sends one.
        body = (ROOT / 'server' / 'app.py').read_text(encoding='utf-8')
        start = body.index("if p == '/api/agent':")
        self.assertIn("d.get('language')", body[start:start + 1400])


class ConversationalPromptTests(unittest.TestCase):
    """The prompt asks for an assistant, not a quote from the page."""

    def setUp(self):
        body = (ROOT / 'server' / 'agent.py').read_text(encoding='utf-8')
        self.prompt = body[body.index('SYSTEM_PROMPT = ('):body.index('LANGUAGE_NAMES = ')]

    def test_it_may_use_general_professional_knowledge(self):
        self.assertIn('general professional knowledge', self.prompt)

    def test_the_one_thing_it_may_not_invent_is_axiasoft(self):
        self.assertIn('must not invent is what AXIASOFT', self.prompt)

    def test_it_is_told_not_to_paste_the_source_text(self):
        self.assertIn('Never quote the PUBLISHED text verbatim', self.prompt)

    def test_length_follows_the_question(self):
        self.assertIn('Length follows the question', self.prompt)
        # The old absolute limits are gone: four sentences and no lists turned a
        # "help me choose" into a clipped fragment.
        self.assertNotIn('Keep it to at most four sentences', self.prompt)
        self.assertNotIn('no bullet lists', self.prompt)

    def test_the_reply_budget_is_not_a_paragraph(self):
        body = (ROOT / 'server' / 'agent.py').read_text(encoding='utf-8')
        call = body[body.index("body = json.dumps({'model'"):]
        call = call[:call.index('.encode')]
        self.assertIn("'max_tokens': 800", call)


class GreetingTests(unittest.TestCase):
    """A greeting is a greeting only when that is all it is."""

    def test_a_bare_greeting_is_a_greeting(self):
        engine = xiona_engine.Engine().add(
            {'id': 'a', 'title': 't', 'topic': 'x', 'route': '#/',
             'text': 'xiona assistant site content', 'language': 'en'})
        for question in ('سلام', 'چطوری', 'hi', 'hello', 'hello there',
                         'how are you doing today'):
            self.assertEqual(engine.answer(question, language=None)['source'],
                             'greeting', question)

    def test_a_greeting_that_opens_a_question_is_not_a_greeting(self):
        engine = xiona_engine.Engine().add(
            {'id': 'a', 'title': 't', 'topic': 'x', 'route': '#/',
             'text': 'xiona assistant site content about websites', 'language': 'en'})
        # 'چطوری سایت بسازیم' = "how do we build a site". It tokenizes to two
        # words once the spoken question words are function words, and the old
        # `len(tokenize(query)) <= 2` guard answered it with "Hello, I am Xiona".
        for question in ('چطوری سایت بسازیم', 'سلام، قیمت چنده؟',
                         'hello, how much does a site cost'):
            self.assertNotEqual(engine.answer(question, language=None)['source'],
                                'greeting', question)

    def test_chitoori_is_not_a_function_word(self):
        # It is the question ("how are you?"), not the frame around one.
        self.assertNotIn('چطوری', xiona_engine.STOPWORDS['fa'])
        js = (ROOT / 'public' / 'xiona.js').read_text(encoding='utf-8')
        block = js[js.index('fa:'):js.index('en:')]
        self.assertNotIn("'چطوری'", block)


class EnvFileTests(unittest.TestCase):
    """.env is found wherever the operator put it."""

    def test_a_file_beside_the_working_directory_is_found(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / '.env').write_text('AXIA_TEST_ROUND30=found\n', encoding='utf-8')
            previous = os.getcwd()
            os.environ.pop('AXIA_TEST_ROUND30', None)
            try:
                os.chdir(tmp)
                loaded = agent.load_env_file()
            finally:
                os.chdir(previous)
                os.environ.pop('AXIA_TEST_ROUND30', None)
        self.assertEqual(loaded.get('AXIA_TEST_ROUND30'), 'found')

    def test_a_real_environment_variable_wins(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / '.env').write_text('AXIA_TEST_ROUND30=file\n', encoding='utf-8')
            with mock.patch.dict(os.environ, {'AXIA_TEST_ROUND30': 'shell'}):
                loaded = agent.load_env_file(str(Path(tmp) / '.env'))
                # Checked inside the patch: mock.patch.dict restores the whole
                # environment on exit, so asserting afterwards asserts nothing.
                self.assertEqual(os.environ.get('AXIA_TEST_ROUND30'), 'shell')
                self.assertNotIn('AXIA_TEST_ROUND30', loaded)

    def test_the_key_is_not_in_git(self):
        ignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
        self.assertIn('.env', ignore.splitlines())

    def test_startup_reports_the_model_and_proves_it(self):
        body = (ROOT / 'server' / 'app.py').read_text(encoding='utf-8')
        self.assertIn('_report_assistant()', body)
        # It must make a real call, not merely say a key is present.
        start = body.index('def _report_assistant')
        section = body[start:body.index('def main', start)]
        self.assertIn("agent.answer(" , section)
        self.assertIn('model OK', section)


class RefusalFallsBackToTheModelTests(unittest.TestCase):
    """A question the site cannot answer must reach the model, not a refusal."""

    def test_the_model_is_asked_even_when_retrieval_finds_nothing(self):
        body = (ROOT / 'server' / 'agent.py').read_text(encoding='utf-8')
        start = body.index('def answer(')
        section = body[start:body.index('\ndef status(', start)]
        # The context is a whole-site summary when retrieval came back empty.
        self.assertIn('index.summary()', section)
        self.assertIn("context = '\\n'.join", section)


if __name__ == '__main__':
    unittest.main()
