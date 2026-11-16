"""Does the configured model actually answer?

A key in the environment and a model that replies are two different things, and
the gap between them is silent by design: when the provider fails, Xiona falls
back to the on-site answer, so the site keeps working and nothing looks broken.
That is the right behaviour for a visitor and a trap for an operator — a revoked
key, a model ID Google has shut down, and a host with no route to the provider
all produce a site that appears healthy while no visitor ever reaches the model.

`status()` therefore reports `model_state`, and these tests pin the four values.

No test here makes a network call. The provider is replaced with a stub, so the
suite is deterministic and needs no key.
"""
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
import agent  # noqa: E402

# The database module is optional here: these tests read the committed files the
# build produces, not a live database.
try:
    import db as db_module
except Exception:  # pragma: no cover - importable in this repo
    db_module = None

CONFIGURED = {
    'AXIA_AGENT_KEY': 'test-key-not-real',
    'AXIA_AGENT_URL': 'https://generativelanguage.googleapis.com/v1beta/openai',
    'AXIA_AGENT_MODEL': 'gemini-3.8-flash',
}


class ModelStateTest(unittest.TestCase):
    def setUp(self):
        # Each test starts from a provider that has not been called yet.
        agent._LAST_CALL.update(ok=None, error=None, at=None)
        self.addCleanup(agent._LAST_CALL.update, ok=None, error=None, at=None)

    def state(self):
        return agent.status()['model_state']

    def test_no_key_is_unconfigured(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('AXIA_AGENT_KEY', None)
            self.assertEqual(self.state(), 'unconfigured')

    def test_a_key_nobody_has_tried_is_untested_not_ok(self):
        # The bug this replaces: 'model' was reported from the presence of a key
        # alone, so a key that had never once worked looked like a working one.
        with mock.patch.dict(os.environ, CONFIGURED):
            self.assertEqual(self.state(), 'untested')

    def test_a_successful_call_is_ok(self):
        with mock.patch.dict(os.environ, CONFIGURED):
            agent._record_success()
            doc = agent.status()
            self.assertEqual(doc['model_state'], 'ok')
            self.assertIsNone(doc['model_last_error'])
            self.assertTrue(doc['model_last_call'])

    def test_a_failed_call_is_failing_and_names_the_reason(self):
        with mock.patch.dict(os.environ, CONFIGURED):
            agent._record_failure('provider returned 401')
            doc = agent.status()
            self.assertEqual(doc['model_state'], 'failing')
            self.assertEqual(doc['model_last_error'], 'provider returned 401')

    def test_a_later_success_clears_an_earlier_failure(self):
        # A provider that was briefly unreachable must not stay marked broken.
        with mock.patch.dict(os.environ, CONFIGURED):
            agent._record_failure('URLError')
            agent._record_success()
            doc = agent.status()
            self.assertEqual(doc['model_state'], 'ok')
            self.assertIsNone(doc['model_last_error'])

    def test_the_state_is_none_of_the_above_without_a_key(self):
        # A stale error from a previous configuration must not leak into a
        # console that is now running without a provider at all.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('AXIA_AGENT_KEY', None)
            agent._record_failure('provider returned 401')
            doc = agent.status()
            self.assertEqual(doc['model_state'], 'unconfigured')
            self.assertIsNone(doc['model_last_error'])
            self.assertIsNone(doc['model'])


class ProviderFailureTest(unittest.TestCase):
    """Every failure path records why, and never leaks the key."""

    def setUp(self):
        agent._LAST_CALL.update(ok=None, error=None, at=None)
        self.addCleanup(agent._LAST_CALL.update, ok=None, error=None, at=None)

    def ask(self, side_effect):
        with mock.patch.dict(os.environ, CONFIGURED), \
                mock.patch('urllib.request.urlopen', side_effect=side_effect):
            return agent.ask_provider('قیمت سایت چقدر است؟', language='fa')

    def test_an_http_error_records_its_status(self):
        error = urllib.error.HTTPError('u', 401, 'Unauthorized', {}, None)
        text, reason = self.ask(error)
        self.assertIsNone(text)
        self.assertEqual(reason, 'provider returned 401')
        self.assertEqual(agent._LAST_CALL['error'], 'provider returned 401')
        self.assertFalse(agent._LAST_CALL['ok'])

    def test_a_network_error_records_its_type(self):
        text, reason = self.ask(urllib.error.URLError('no route to host'))
        self.assertIsNone(text)
        self.assertEqual(reason, 'URLError')
        self.assertEqual(agent._LAST_CALL['error'], 'URLError')

    def test_a_timeout_records_its_type(self):
        text, reason = self.ask(TimeoutError('too slow'))
        self.assertIsNone(text)
        self.assertEqual(reason, 'TimeoutError')

    def test_an_empty_answer_counts_as_a_failure(self):
        # A 200 with no content is not a usable answer; reporting it as success
        # would leave the console green while the visitor got nothing.
        class Response:
            def __init__(self, payload):
                self.payload = payload
            def read(self):
                return self.payload
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return False
        payload = b'{"choices": [{"message": {"content": "   "}}]}'
        # The status call has to stay inside the patched environment: outside
        # it there is no key and the state reads 'unconfigured', which would
        # pass the wrong assertion for the right reason.
        with mock.patch.dict(os.environ, CONFIGURED):
            text, reason = self.ask(lambda *a, **k: Response(payload))
            self.assertIsNone(text)
            self.assertEqual(reason, 'empty response')
            self.assertEqual(agent.status()['model_state'], 'failing')

    def test_a_good_answer_is_recorded_as_success(self):
        class Response:
            def read(self):
                return b'{"choices": [{"message": {"content": "hello"}}]}'
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return False
        with mock.patch.dict(os.environ, CONFIGURED), \
                mock.patch('urllib.request.urlopen', return_value=Response()):
            text, reason = agent.ask_provider('hi', language='en')
            self.assertEqual(text, 'hello')
            self.assertIsNone(reason)
            self.assertEqual(agent.status()['model_state'], 'ok')

    def test_the_key_is_never_part_of_the_reason(self):
        # The reason string is served to the browser; a key echoed back by the
        # provider must not reach it.
        error = urllib.error.HTTPError('u', 400, 'Bad Request', {}, None)
        text, reason = self.ask(error)
        self.assertNotIn('test-key-not-real', str(reason))
        self.assertNotIn('test-key-not-real', str(agent.status()))

    def test_a_failure_falls_back_to_the_on_site_answer(self):
        # The visitor must still get an answer, and it must be labelled as
        # on-site rather than passed off as the model's.
        error = urllib.error.HTTPError('u', 401, 'Unauthorized', {}, None)
        with mock.patch.dict(os.environ, CONFIGURED), \
                mock.patch('urllib.request.urlopen', side_effect=error), \
                mock.patch.object(agent, 'engine') as fake:
            fake.return_value.answer.return_value = {
                'answer': 'on-site answer', 'language': 'fa', 'citations': [],
            }
            fake.return_value.summary.return_value = 'summary'
            result = agent.answer('قیمت سایت؟', language='fa')
        self.assertEqual(result['provider'], 'on-site')
        self.assertEqual(result['answer'], 'on-site answer')
        self.assertEqual(result['detail'], 'provider returned 401')


class DocumentedModelTest(unittest.TestCase):
    """The example model in the docs must not be one Google has shut down.

    `gemini-2.0-flash` was the documented default and stopped answering on
    2026-06-01, so anyone who followed the README exactly got a provider that
    never replied — and, thanks to the silent fallback, a site that looked fine.
    """

    SUBMITTED = ['README.md', 'docs/agent.md', '.env.example', 'server/agent.py']

    def test_no_document_recommends_a_shut_down_model_as_the_example(self):
        for name in self.SUBMITTED:
            text = (ROOT / name).read_text(encoding='utf-8')
            for line in text.splitlines():
                stripped = line.strip()
                # A commented warning, a table row or prose may mention the old
                # name to explain that it is gone. What must never happen is a
                # line that *configures* it — that is the one a reader copies.
                if stripped.startswith('#') or stripped.startswith('|'):
                    continue
                if 'gemini-2.0-flash' not in stripped:
                    continue
                configures = ('=' in stripped and not stripped.startswith('`'))
                self.assertFalse(
                    configures,
                    f'{name} still sets gemini-2.0-flash, shut down 2026-06-01: {stripped!r}')

    def test_every_document_agrees_on_the_model(self):
        names = {}
        for name in self.SUBMITTED:
            text = (ROOT / name).read_text(encoding='utf-8')
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                if 'AXIA_AGENT_MODEL=' in stripped:
                    names[name] = stripped.split('AXIA_AGENT_MODEL=', 1)[1].split()[0].strip('`')
        self.assertGreaterEqual(len(names), 2, 'expected the model name in several files')
        self.assertEqual(len(set(names.values())), 1,
                         f'the docs disagree about the model: {names}')
        self.assertTrue(all(v.startswith('gemini-') for v in names.values()), names)


class SiteKnowledgeTest(unittest.TestCase):
    """The assistant must know the site on a fresh install.

    The reported bug: Xiona answered every question with "I have no knowledge
    yet — once a product or article is published I will read it", including
    questions about AURION, which the site has a whole page about. The cause was
    not the model and not the key: the index was empty. A fresh install seeds no
    products (SEED_PRODUCTS is deliberately empty) and publishes no articles, and
    the server passed neither page copy nor the site dictionary to the engine —
    only the static build did. So the server's assistant knew nothing that was
    not in the database.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.original = db_module.DB_PATH if db_module else agent.CONTENT_PROVIDERS
        # Point the agent at the committed files the build produces.
        cls.saved_providers = agent.CONTENT_PROVIDERS
        agent.configure_content(lambda: [], lambda: [], lambda: ('test',))

    @classmethod
    def tearDownClass(cls):
        agent.configure_content(*cls.saved_providers) if cls.saved_providers else None
        cls.tmp.cleanup()

    def index(self):
        return agent.engine()

    def test_the_committed_site_pages_are_in_the_index(self):
        stats = self.index().stats()
        self.assertGreater(stats['chunks'], 0, 'a fresh install indexed nothing')

    def test_aurion_is_indexed(self):
        # The page the assistant advertised and could not answer about.
        stats = self.index().stats()
        self.assertIn('aurion', stats['topics'])

    def test_it_answers_a_question_about_aurion(self):
        result = self.index().answer('اوریون چیست؟', language='fa')
        self.assertEqual(result['source'], 'knowledge')
        answer = result['answer']
        self.assertIn('MetaTrader', answer + ' '.join(
            str(c.get('title')) for c in result['citations']))
        self.assertNotIn('هنوز دانشی', answer)

    def test_it_does_not_claim_to_know_nothing(self):
        # The exact symptom that was reported.
        for question, language in (('اوریون چیست؟', 'fa'),
                                   ('what is AURION?', 'en'),
                                   ('چه خدماتی ارائه می‌دهید؟', 'fa')):
            answer = self.index().answer(question, language=language)['answer']
            self.assertNotIn('هنوز دانشی', answer)
            self.assertNotIn('I have no knowledge yet', answer)

    def test_the_refund_policy_is_still_reachable(self):
        result = self.index().answer('سیاست بازپرداخت چیست؟', language='fa')
        self.assertEqual(result['source'], 'knowledge')
        self.assertIn('14', result['answer'])

    def test_the_persian_faq_answers_are_indexed(self):
        # The FAQ lives in settings, not on a page function, so it needs its own
        # way into the index.
        statements = ' '.join(
            str(d.get('text') or '') for d in self.index().docs)
        self.assertTrue('AURION' in statements or 'اوریون' in statements)

    def test_the_word_list_crosses_languages(self):
        # Without the pairs, a Persian question cannot reach English page copy.
        pairs = agent.site_pairs()
        self.assertGreater(len(pairs), 100)

    def test_committed_articles_are_indexed_off_the_database(self):
        # data/articles.json is committed; the database is empty on a fresh
        # checkout, and the assistant knew about none of those posts.
        articles = agent.committed_articles()
        self.assertGreaterEqual(len(articles), 2)
        self.assertTrue(all(a.get('status') == 'published' for a in articles))

    def test_the_two_engines_share_one_stopword_list(self):
        # The Python server and the browser assistant are the same assistant,
        # and their stopword lists had drifted: the browser knew «دهید» was a
        # light verb, the server did not, so the server attached the word to
        # payments and fell below its own coverage gate on «چه خدماتی ارائه
        # می‌دهید؟» — a question it had answered a round earlier.
        import re
        import xiona_engine
        source = (ROOT / 'public' / 'xiona.js').read_text(encoding='utf-8')
        block = source[source.index("fa: ["):source.index("en: [")]
        browser = set(re.findall(r"'([^']+)'", block))
        self.assertEqual(browser, xiona_engine.STOPWORDS['fa'])

    def test_a_question_built_on_a_light_verb_still_answers(self):
        result = self.index().answer('چه خدماتی ارائه می‌دهید؟', language='fa')
        self.assertEqual(result['source'], 'knowledge')

    def test_the_snapshot_carries_the_page_copy(self):
        pages = agent.site_pages()
        topics = {str(p.get('topic')) for p in pages if isinstance(p, dict)}
        self.assertIn('aurion', topics)
        self.assertIn('services', topics)


if __name__ == '__main__':
    unittest.main()
