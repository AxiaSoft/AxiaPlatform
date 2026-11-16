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
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
import agent  # noqa: E402

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


if __name__ == '__main__':
    unittest.main()
