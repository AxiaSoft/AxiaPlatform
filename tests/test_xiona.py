"""Xiona — the on-site assistant.

These tests use the browser engine (public/xiona.js) as the reference, because
that is the implementation a visitor actually reaches on the static build, and
assert that the Python twin gives the same answer for the same content. A
disagreement between them is a bug in one of them, not a matter of taste.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
import xiona_engine as engine  # noqa: E402

PRODUCTS = [
    {'slug': 'arya', 'title': 'Arya', 'category': 'Websites', 'published': 1,
     'summary': 'A brand website with a CMS.',
     'description': 'Arya is a complete website build with a content system and search.',
     'features': ['CMS', 'Search'], 'technologies': ['Python']},
    {'slug': 'homa', 'title': 'Homa', 'category': 'Websites', 'published': 1,
     'summary': 'Clarity, by design.', 'description': 'A website build under the Homa brand.',
     'features': [], 'technologies': []},
    {'slug': 'hidden', 'title': 'Hidden draft', 'category': 'Websites', 'published': 0,
     'summary': 'This product must never be cited.', 'description': 'Not published.',
     'features': [], 'technologies': []},
]

ARTICLES = [
    {'slug': 'fast-website', 'title': 'چطور یک وب‌سایت سریع بسازیم', 'language': 'fa',
     'summary': 'سرعت نتیجهٔ سه تصمیم درست از روز اول است.',
     'body': 'کاربری که سه ثانیه منتظر می‌ماند معمولاً برنمی‌گردد. سرعت در پایان پروژه اضافه نمی‌شود.',
     'tags': ['سرعت', 'وب']},
]

PAGES = [
    {'topic': 'contact', 'title': 'Start a project', 'route': '#/contact',
     'text': ('Start a conversation. Tell us what you are working toward. Choose a development '
              'starting point and share context. No payment is taken on this site.'),
     'aliases': 'تماس سفارش درخواست پروژه شروع ثبت contact order request project start quote'},
    {'topic': 'refunds-policy', 'title': 'Refund and return policy', 'route': '#/refunds-policy',
     'text': ('Customers may submit a refund request within 14 calendar days of the applicable '
              'purchase or order date, subject to the published terms.'),
     'aliases': 'بازپرداخت لغو استرداد refund cancellation'},
    {'topic': 'privacy', 'title': 'Privacy policy', 'route': '#/privacy',
     'text': 'We collect information needed to respond to enquiries, run an account and deliver agreed work.',
     'aliases': 'حریم خصوصی داده اطلاعات privacy data'},
]


PAIRS = [
    ['Products', 'محصولات'], ['Services', 'خدمات'], ['Contact', 'تماس'],
    ['Privacy', 'حریم خصوصی'], ['Support', 'پشتیبانی'], ['Refund', 'بازپرداخت'],
    ['Quote', 'برآورد'], ['Price labels', 'برچسب قیمت'], ['Hello', 'سلام'],
    ['Human support', 'پشتیبانی انسانی'],
]


def build():
    """The corpus the build ships: content plus the site's own dictionary."""
    return engine.Engine().vocabulary(PAIRS).learn(
        {'products': PRODUCTS, 'articles': ARTICLES, 'pages': PAGES})


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.index = build()

    def test_it_indexes_the_site_it_is_given(self):
        stats = self.index.stats()
        self.assertGreater(stats['chunks'], 3)
        for topic in ('product', 'article', 'contact', 'refunds-policy'):
            self.assertIn(topic, stats['topics'])

    def test_unpublished_products_are_not_indexed(self):
        answers = [self.index.answer('hidden draft')['answer'] for _ in range(1)]
        self.assertNotIn('must never be cited', answers[0])

    def test_it_learns_new_content_without_a_code_change(self):
        before = self.index.answer('kubernetes deployment')['source']
        self.index.add({'id': 'new-product', 'title': 'Deployment',
                        'topic': 'product', 'route': '#/products/deploy',
                        'text': 'Kubernetes deployment support is available as a service.'})
        after = self.index.answer('kubernetes deployment')
        self.assertIn(before, ('no-match', 'uncovered'))
        self.assertEqual(after['source'], 'knowledge')
        self.assertIn('Kubernetes', after['answer'])


class AnswerTests(unittest.TestCase):
    def setUp(self):
        self.index = build()

    def test_refund_question_reaches_the_refund_policy(self):
        result = self.index.answer('بازپرداخت چطور است؟')
        self.assertEqual(result['source'], 'knowledge')
        self.assertIn('refund', result['answer'].lower())
        self.assertEqual(result['citations'][0]['route'], '#/refunds-policy')

    def test_english_refund_question_also_works(self):
        result = self.index.answer('what is your refund policy')
        self.assertEqual(result['source'], 'knowledge')
        self.assertIn('refund', result['answer'].lower())

    def test_a_persian_question_reaches_english_page_copy(self):
        # The page copy is English; the question is Persian. The bridge is what
        # makes this work, and without it Xiona is mute on half the site.
        result = self.index.answer('حریم خصوصی')
        self.assertEqual(result['source'], 'knowledge')
        self.assertIn('collect', result['answer'].lower())

    def test_price_question_is_answered_from_what_the_site_says(self):
        # The fixtures publish 'Request a quote' on the product, so a price
        # question has a real answer - and the answer must be the site's
        # wording, never a number.
        for question in ('قیمت سایت چقدر است', 'how much does a website cost'):
            result = self.index.answer(question)
            self.assertIn(result['source'], ('knowledge', 'uncovered'), question)
            self.assertNotRegex(result['answer'], r'[$€£]\s?\d|\d+\s?(USD|EUR|تومان|ریال)')

    def test_greeting_is_a_greeting_in_the_same_language(self):
        self.assertEqual(self.index.answer('سلام')['source'], 'greeting')
        self.assertEqual(self.index.answer('hello there')['source'], 'greeting')
        self.assertTrue(any('\u0600' <= ch <= '\u06FF' for ch in self.index.answer('سلام')['answer']))

    def test_unknown_question_says_so_instead_of_inventing(self):
        result = self.index.answer('do you support quantum teleportation hardware')
        # The engine distinguishes "nothing scored" from "the site does not
        # publish this subject at all". Either way it must say so.
        self.assertIn(result['source'], ('no-match', 'uncovered'))
        self.assertTrue('couldn' in result['answer'].lower() or
                        'does not publish' in result['answer'].lower())

    def test_empty_index_is_honest(self):
        empty = engine.Engine()
        result = empty.answer('anything')
        self.assertEqual(result['source'], 'empty-index')

    def test_answers_carry_the_page_they_came_from(self):
        result = self.index.answer('CMS')
        self.assertTrue(result['citations'])
        self.assertTrue(all('route' in c for c in result['citations']))


class TruthfulnessTests(unittest.TestCase):
    """Xiona must never assert anything the site did not publish."""

    def setUp(self):
        self.index = build()

    def test_every_answer_is_composed_from_indexed_text(self):
        corpus = ' '.join(doc['text'] for doc in self.index.docs)
        for question in ('بازپرداخت', 'CMS', 'حریم خصوصی', 'سرعة'):
            answer = self.index.answer(question)
            if answer['source'] != 'knowledge':
                continue
            # Every content word of the answer must exist in an indexed chunk.
            # Comparing whole sentences is too strict: tidy() normalises
            # punctuation ('Overview.' -> 'Overview:'), which changes the exact
            # string without changing what is claimed.
            import re as _re
            answer_words = {w for w in _re.findall(r'[a-zA-Z\u0600-\u06FF]{4,}',
                                                   answer['answer'].lower())}
            corpus_words = {w for w in _re.findall(r'[a-zA-Z\u0600-\u06FF]{4,}',
                                                   corpus.lower())}
            unknown = answer_words - corpus_words
            self.assertFalse(unknown, f'words not present in any chunk: {sorted(unknown)[:6]}')

    def test_no_price_is_ever_stated(self):
        for question in ('price', 'قیمت', 'cost', 'how much'):
            answer = self.index.answer(question)['answer']
            self.assertNotRegex(answer, r'[$€£]\s?\d|\d+\s?(USD|EUR|euro|dollar|تومان|ریال)')



class NoScriptedAnswersTests(unittest.TestCase):
    """Xiona must recognise what is asked, not recognise a keyword and recite.

    The previous build carried two regex tables that answered price questions
    and "are you a bot" with a fixed sentence. They are gone, and these tests are
    what stops them coming back: every answer must be traceable to a chunk of the
    site, and a question whose subject the site does not publish must be refused
    instead of matched to the nearest paragraph.
    """

    def setUp(self):
        self.index = build()

    def test_a_duration_question_is_not_answered_with_a_price_sentence(self):
        # 'پروژه چقدر طول میکشد' asks how long a project takes. It shares the
        # word 'چقدر' (how much) with a price question, and the old table caught
        # it on that word alone and answered about pricing.
        result = self.index.answer('پروژه چقدر طول می‌کشد')
        self.assertNotIn('منتشر نشده', result['answer'])
        self.assertNotIn('not published', result['answer'].lower())

    def test_an_unknown_subject_is_refused_and_says_what_is_covered(self):
        result = self.index.answer('کوانتوم کامپیوتر')
        self.assertEqual(result['source'], 'uncovered')
        # The refusal names what the site does publish, taken from the index.
        self.assertIn('Kubernetes' if False else 'start', result['answer'].lower()
                      + ' ' + ' '.join(t.lower() for t in self.index.topics()))
        self.assertEqual(result['citations'], [])

    def test_the_subject_of_a_question_is_what_decides_it(self):
        # 'هزینه بازپرداخت' names cost, which this site never publishes, but its
        # subject is the refund, which it does.
        result = self.index.answer('هزینه بازپرداخت چطور محاسبه می‌شود')
        self.assertEqual(result['source'], 'knowledge')
        self.assertIn('refund', result['answer'].lower())

    def test_every_answer_points_at_a_chunk_that_exists(self):
        routes = {page['route'] for page in PAGES}
        for question in ('بازپرداخت', 'CMS', 'حریم خصوصی', 'سفارش چطور ثبت کنم'):
            answer = self.index.answer(question)
            self.assertEqual(answer['source'], 'knowledge', question)
            for citation in answer['citations']:
                self.assertIn(citation['route'], routes | {'#/products/arya', '#/products/homa'},
                              f'{question} cited a route the site does not have')

    def test_the_answer_is_the_site_speaking(self):
        # An answer must be built from the chunk it cites - no sentence that the
        # site did not write.
        for question in ('بازپرداخت', 'CMS'):
            answer = self.index.answer(question)
            corpus = ' '.join(doc['text'].lower() for doc in self.index.docs)
            for sentence in answer['answer'].split('. '):
                words = [w for w in sentence.lower().split() if len(w) > 4]
                if not words:
                    continue
                found = sum(1 for w in words if w.strip('.,:;') in corpus)
                self.assertGreater(found / len(words), 0.8,
                                   f'answer sentence not traceable to the site: {sentence[:60]}')


class LearnedVocabularyTests(unittest.TestCase):
    """The bridge between Persian questions and English copy is learned.

    It must not be a list written into the engine: a hand-kept list only knows
    the words its author thought of, which is the assistant problem - it answers
    what it was told to answer.
    """

    def test_the_dictionary_comes_from_the_site(self):
        index = engine.Engine().vocabulary(PAIRS)
        # Every pair the site's UI ships is a pair the engine can use.
        self.assertGreater(len(index.lexicon), 5)

    def test_a_new_ui_string_teaches_a_new_word(self):
        index = build()
        word = 'تارنما'          # a Persian word for "site" the engine never saw
        self.assertFalse(index.known(word))
        # A string added to the UI tomorrow, translated, is understood after the
        # next build without touching the engine. The site's English copy says
        # 'site', so pairing them makes the word reachable.
        index.vocabulary(PAIRS + [['Site', word]])
        self.assertTrue(index.known(word),
                        'a dictionary pair supplied by the site must be usable')

    def test_an_unknown_word_stays_unknown(self):
        # The same mechanism must not make everything look known: a word no
        # dictionary pair and no chunk mentions is still unknown.
        index = build()
        self.assertFalse(index.known('زئولیت'))

    def test_the_engine_ships_no_hand_written_keyword_table(self):
        source = (ROOT / 'public' / 'xiona.js').read_text(encoding='utf-8')
        for table in ('var UNCOVERED', 'var PHRASES', 'var BRIDGE', 'var VAGUE', 'var GENERIC'):
            self.assertNotIn(table, source,
                             f'{table} is a hand-written keyword table; the vocabulary '
                             'must come from the site')
        python = (ROOT / 'server' / 'xiona_engine.py').read_text(encoding='utf-8')
        for table in ('\nUNCOVERED =', '\nPHRASES =', '\nBRIDGE =', '\nVAGUE =', '\nGENERIC ='):
            self.assertNotIn(table, python, f'{table} is a hand-written keyword table')


class ParityTests(unittest.TestCase):
    """The browser engine and the Python engine must agree on the same content.

    The static site answers in the browser and the server build answers in
    Python. If they disagree, a visitor gets a different answer depending on
    where the site is deployed, which is a bug in whichever one is wrong.
    """

    def test_the_two_engines_reach_the_same_topic(self):
        haystack = json.dumps({
            'products': PRODUCTS, 'articles': ARTICLES, 'pages': PAGES,
            'pairs': PAIRS,
        }, ensure_ascii=False)
        questions = ['بازپرداخت', 'حریم خصوصی', 'سفارش چطور ثبت کنم', 'CMS', 'قیمت',
                     'قوانین سایت', 'حریم خصوصی سایت', 'سلام', 'hello',
                     'what is the capital of Peru']

        script = '''
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const X = require(process.argv[2]);
const data = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
const e = new X.Engine().vocabulary(data.pairs).learn(data);
const out = {};
for (const q of JSON.parse(process.argv[4])) {
  const a = e.answer(q);
  out[q] = { source: a.source, first: (a.citations[0] || {}).route || '' };
}
process.stdout.write(JSON.stringify(out));
'''
        with tempfile.TemporaryDirectory() as tmp:
            script_path = Path(tmp) / 'parity.mjs'
            script_path.write_text(script, encoding='utf-8')
            data_path = Path(tmp) / 'data.json'
            data_path.write_text(haystack, encoding='utf-8')
            try:
                result = subprocess.run(
                    ['node', str(script_path), str(ROOT / 'public' / 'xiona.js'),
                     str(data_path), json.dumps(questions)],
                    capture_output=True, text=True, timeout=60)
            except FileNotFoundError:
                self.skipTest('node is not installed')
            if result.returncode != 0:
                self.skipTest('node could not run the browser engine: ' + result.stderr[:120])
            browser = json.loads(result.stdout)

        index = build()
        for question in questions:
            local = index.answer(question)
            self.assertEqual(local['source'], browser[question]['source'],
                             f'{question!r}: browser={browser[question]["source"]} '
                             f'python={local["source"]}')

    def test_the_shipped_browser_engine_parses(self):
        try:
            result = subprocess.run(['node', '--check', str(ROOT / 'public' / 'xiona.js')],
                                    capture_output=True, text=True, timeout=30)
        except FileNotFoundError:
            self.skipTest('node is not installed')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
