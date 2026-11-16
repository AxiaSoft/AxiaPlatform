"""Blog rendering, validation and the support agent."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import agent  # noqa: E402
import blog  # noqa: E402


class MarkdownTest(unittest.TestCase):
    def test_headings_shrink_because_the_page_owns_h1(self):
        self.assertIn('<h2>', blog.render_markdown('# One'))
        self.assertIn('<h3>', blog.render_markdown('## Two'))

    def test_inline_formatting(self):
        html = blog.render_markdown('**bold** and *italic* and `code`')
        self.assertIn('<strong>bold</strong>', html)
        self.assertIn('<em>italic</em>', html)
        self.assertIn('<code>code</code>', html)

    def test_lists_and_quotes(self):
        html = blog.render_markdown('- a\n- b\n\n> quoted')
        self.assertIn('<ul><li>a</li><li>b</li></ul>', html)
        self.assertIn('<blockquote>', html)

    def test_links_only_allow_http_and_site_paths(self):
        safe = blog.render_markdown('[ok](https://example.com)')
        self.assertIn('href="https://example.com"', safe)
        unsafe = blog.render_markdown('[bad](javascript:alert(1))')
        self.assertNotIn('javascript:', unsafe)
        self.assertNotIn('<a', unsafe)

    def test_html_in_the_body_is_escaped(self):
        html = blog.render_markdown('<script>alert(1)</script>')
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_fenced_code_is_escaped(self):
        html = blog.render_markdown('```\n<b>x</b>\n```')
        self.assertIn('<pre><code>', html)
        self.assertIn('&lt;b&gt;', html)

    def test_reading_time_never_reports_zero(self):
        self.assertEqual(blog.reading_minutes('short'), 1)

    def test_slugify_is_ascii_and_dash_separated(self):
        self.assertEqual(blog.slugify('Hello There World!'), 'hello-there-world')
        self.assertEqual(blog.slugify('سلام دنیا'), '')


class ValidationTest(unittest.TestCase):
    def test_a_short_title_is_rejected(self):
        _, errors = blog.clean_article({'title': 'a', 'body': 'x' * 100})
        self.assertIn('title', errors)

    def test_a_body_must_carry_words_not_markup(self):
        _, errors = blog.clean_article({'title': 'Reasonable title', 'body': '# --- ###'})
        self.assertIn('body', errors)

    def test_tags_split_from_a_comma_string_and_cap_at_six(self):
        values, _ = blog.clean_article({'title': 'A real title', 'body': 'x' * 90,
                                        'tags': 'a, b, c, d, e, f, g'})
        self.assertEqual(len(values['tags']), 6)
        self.assertEqual(values['tags'][0], 'a')

    def test_an_unknown_status_falls_back_to_draft(self):
        values, _ = blog.clean_article({'title': 'A real title', 'body': 'x' * 90,
                                        'status': 'shout-it'})
        self.assertEqual(values['status'], 'draft')


class AgentTest(unittest.TestCase):
    """The support agent, now backed by the on-site engine.

    Xiona used to answer from ten hand-written facts. It now learns from the
    site's own published content (products, articles, page copy), so these tests
    seed that content rather than asserting keyword lists.
    """

    @classmethod
    def setUpClass(cls):
        product = {
            'id': 1, 'slug': 'arya', 'title': 'Arya', 'category': 'Websites',
            'summary': 'A brand website with a CMS.',
            'description': 'Arya is a complete website build with a content system.',
            'features': ['CMS'], 'technologies': ['Python'], 'published': 1,
            'price_label': 'Request a quote', 'status': 'available',
        }
        article = {
            'slug': 'fast-website', 'title': 'چطور یک وب‌سایت سریع بسازیم',
            'language': 'fa', 'summary': 'سرعت نتیجهٔ سه تصمیم درست از روز اول است.',
            'body': 'کاربری که سه ثانیه منتظر می‌ماند معمولاً برنمی‌گردد.',
            'tags': ['سرعت'],
        }
        contact = {
            'topic': 'contact', 'title': 'Start a project', 'route': '#/contact',
            'text': ('Start a conversation and share what you are building. '
                     'You get a reference number immediately.'),
            'aliases': 'تماس سفارش درخواست پروژه شروع ثبت order request project start',
        }
        refunds = {
            'topic': 'refunds-policy', 'title': 'Refund and return policy',
            'route': '#/refunds-policy',
            'text': ('Customers may submit a refund request within 14 calendar days '
                     'of the applicable purchase or order date.'),
            'aliases': 'بازپرداخت لغو استرداد refund cancellation',
        }
        agent.configure_content(
            lambda: [product], lambda: [article],
            lambda: ('seeded',))

        import xiona_engine
        xiona_engine._engine = xiona_engine.Engine().learn({
            'products': [product], 'articles': [article],
            'pages': [contact, refunds],
        })
        xiona_engine._content_stamp = ('seeded',)

    def test_it_answers_a_known_topic(self):
        result = agent.answer('how do I start a project?')
        self.assertEqual(result['source'], 'knowledge')
        self.assertIn('reference number', result['answer'])

    def test_it_answers_in_persian_keywords(self):
        result = agent.answer('بازپرداخت چطور است؟')
        self.assertEqual(result['source'], 'knowledge')
        self.assertIn('refund', result['answer'].lower())
        self.assertIn('refunds-policy', result['topics'])

    def test_it_admits_ignorance_rather_than_inventing(self):
        result = agent.answer('what is the capital of Peru')
        # 'uncovered' means the site publishes nothing on the subject, which is
        # the honest answer; 'no-match' means nothing scored. Both refuse.
        self.assertIn(result['source'], ('no-match', 'uncovered'))
        self.assertTrue('couldn' in result['answer'].lower() or
                        'does not publish' in result['answer'].lower())

    def test_it_never_mentions_payments_it_cannot_take(self):
        for question in ['refund my order', 'cancel', 'cms']:
            answer = agent.answer(question)['answer']
            self.assertNotIn('I have refunded', answer)
            self.assertNotIn('your payment has', answer)

    def test_status_reports_the_on_site_engine(self):
        os.environ.pop('AXIA_AGENT_KEY', None)
        state = agent.status()
        self.assertEqual(state['provider'], 'local')
        self.assertTrue(state['configured'])
        self.assertEqual(state['engine'], 'on-site')
        self.assertGreater(state['chunks'], 0)


if __name__ == '__main__':
    unittest.main()


class BlogPostResolutionTests(unittest.TestCase):
    """A published post resolves, and a missing one says so properly.

    Two faults, both reported as "I published a post and the link 404s".

    1. The console's "View" link was a raw `href="/blog/<slug>/"`. On GitHub
       Pages the site is served from /AxiaPlatform/, so that link pointed at a
       path that does not exist — the post was there, the URL was wrong. The
       console already had the helper that solves this for brand images; the
       blog link simply did not use it.
    2. A slug that did not resolve was served by handing 404.html to
       serve_static(), which sends any file it finds with 200. So the 404 page
       was the one page that never returned 404 — search engines indexed it and
       browsers cached it.
    """

    def setUp(self):
        self.app_py = (ROOT / 'server' / 'app.py').read_text(encoding='utf-8')
        self.admin_js = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')

    def test_a_missing_post_returns_404(self):
        start = self.app_py.index('def serve_blog(self, path):')
        end = self.app_py.index('def _send_html(', start)
        body = self.app_py[start:end]
        self.assertIn('return self._not_found()', body)
        self.assertNotIn("self.serve_static('/404.html')", body,
                         'serving the 404 page as a file makes it a 200')

    def test_not_found_really_sets_the_status(self):
        start = self.app_py.index('def _not_found(self):')
        body = self.app_py[start:start + 700]
        self.assertIn('send_response(404)', body)

    def test_the_console_links_to_a_post_through_the_base_helper(self):
        self.assertIn('baseUrl(`blog/${esc(a.slug)}/`)', self.admin_js)

    def test_the_console_keeps_one_base_helper(self):
        # brandAsset() used to hold the base logic inline. Two copies would drift
        # apart, and the one that was wrong is exactly what caused this.
        self.assertIn('function baseUrl(path)', self.admin_js)
        self.assertIn('return baseUrl(raw)', self.admin_js)
        self.assertEqual(self.admin_js.count('const fromPath=(location.pathname'), 1)

    def test_the_helper_handles_the_four_cases(self):
        # A path with no prefix gains the base; one that already has it is not
        # prefixed twice; an absolute URL is untouched.
        start = self.admin_js.index('function baseUrl(path)')
        end = self.admin_js.index('\n}', start) + 2
        self.assertIn('if(/^(?:https?:)?\\/\\//i.test(raw))return raw;', self.admin_js[start:end])
        self.assertIn("if(base!=='/'&&raw.startsWith(base))return raw;", self.admin_js[start:end])

    def test_the_storefronts_blog_link_uses_the_base_too(self):
        # The mobile menu had the same raw href, so on Pages the blog was
        # unreachable from a phone for the same reason.
        self.assertNotIn('<a href="/blog/">Blog</a>', self.app_js)
        self.assertIn("assetUrl('blog/')", self.app_js)

    def test_a_draft_is_not_served(self):
        start = self.app_py.index('def serve_blog(self, path):')
        end = self.app_py.index('def _send_html(', start)
        self.assertIn("status='published'", self.app_py[start:end])
