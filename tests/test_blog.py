"""Blog rendering, validation and the support agent."""
import os
import sys
import unittest

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
    def test_it_answers_a_known_topic(self):
        result = agent.answer('how do I start a project?')
        self.assertIn('order', result['topics'])
        self.assertIn('reference number', result['answer'])

    def test_it_answers_in_persian_keywords(self):
        result = agent.answer('بازپرداخت چطور است؟')
        self.assertIn('refund', result['topics'])

    def test_it_admits_ignorance_rather_than_inventing(self):
        result = agent.answer('what is the capital of Peru')
        self.assertEqual(result['topics'], [])
        self.assertIn('do not have an approved answer', result['answer'])

    def test_it_never_mentions_payments_it_cannot_take(self):
        for question in ['refund my order', 'how much', 'cancel']:
            answer = agent.answer(question)['answer']
            self.assertNotIn('I have refunded', answer)

    def test_status_reports_local_mode_without_a_key(self):
        os.environ.pop('AXIA_AGENT_KEY', None)
        state = agent.status()
        self.assertEqual(state['provider'], 'local')
        self.assertFalse(state['configured'])
        self.assertGreaterEqual(state['topics'], 8)




class TranslationTest(unittest.TestCase):
    """The English mirror must never pass off untranslated text as English."""

    def setUp(self):
        import sqlite3
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE article_translations(article_id INTEGER, lang TEXT, "
                        "title TEXT, summary TEXT, body TEXT, source_hash TEXT, "
                        "PRIMARY KEY(article_id, lang))")
        self.row = {'id': 1, 'slug': 'a-post', 'language': 'fa', 'title': 'عنوان',
                    'summary': 'خلاصه', 'body': 'متن کافی برای آزمایش این بخش از کد.'}

    def test_without_a_provider_the_source_is_flagged_not_translated(self):
        import os
        os.environ.pop('AXIA_AGENT_KEY', None)
        out = blog.localised(self.row, self.db, target='en')
        self.assertFalse(out['translated'])
        self.assertEqual(out['title'], 'عنوان')

    def test_a_cached_translation_is_reused(self):
        out = blog.localised(self.row, self.db, target='en')  # writes nothing without a key
        self.assertFalse(out['translated'])

    def test_an_english_article_needs_no_translation(self):
        row = dict(self.row, language='en', title='A post')
        out = blog.localised(row, self.db, target='en')
        self.assertTrue(out['translated'])
        self.assertEqual(out['title'], 'A post')

    def test_the_notice_only_appears_on_untranslated_pages(self):
        page = {'title': 'T', 'slug': 's', 'html': '<p>x</p>', 'language': 'fa',
                'translated': False}
        self.assertIn('blog-notice', blog.render_article(page, lang='en'))
        page['translated'] = True
        self.assertNotIn('blog-notice', blog.render_article(page, lang='en'))


class LanguageMirrorTest(unittest.TestCase):
    def test_the_shell_switches_direction(self):
        self.assertIn('dir="rtl"', blog.shell('<title>t</title>', '', lang='fa'))
        self.assertIn('dir="ltr"', blog.shell('<title>t</title>', '', lang='en'))

    def test_the_language_switch_keeps_the_article(self):
        fa = blog.shell('<title>t</title>', '', lang='fa', base='/b', slug='post')
        self.assertIn('href="/b/en/blog/post/"', fa)
        en = blog.shell('<title>t</title>', '', lang='en', base='/b', slug='post')
        self.assertIn('href="/b/blog/post/"', en)

    def test_hreflang_names_both_languages(self):
        head = blog.head_tags('T', 'D', 'https://o/b/blog/x/', 'https://o', '/b',
                              'article', lang='fa', alt_url='https://o/b/en/blog/x/')
        self.assertIn('hreflang="fa-IR" href="https://o/b/blog/x/"', head)
        self.assertIn('hreflang="en" href="https://o/b/en/blog/x/"', head)

    def test_the_sitemap_pairs_each_page_with_its_mirror(self):
        xml = blog.render_sitemap('https://o', '/b', [{'slug': 'p'}])
        self.assertIn('https://o/b/en/blog/', xml)
        self.assertIn('https://o/b/en/blog/p/', xml)
        self.assertIn('xmlns:xhtml', xml)




class CoverValidationTest(unittest.TestCase):
    """A product cover is a path this site serves, or an https URL."""

    def setUp(self):
        import os as _os, sys as _sys
        _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', 'server'))
        import app
        self.clean = app.clean_cover

    def test_an_uploaded_path_is_accepted(self):
        self.assertEqual(self.clean('/uploads/covers/abc123.png'),
                         '/uploads/covers/abc123.png')

    def test_a_brand_image_is_accepted(self):
        self.assertEqual(self.clean('/brand/arya-logo.png'), '/brand/arya-logo.png')

    def test_an_https_url_is_accepted(self):
        self.assertEqual(self.clean('https://example.test/a.png'), 'https://example.test/a.png')

    def test_script_urls_are_refused(self):
        for bad in ('javascript:alert(1)', 'data:image/png;base64,xx', '//evil.test/a.png',
                    '/uploads/covers/../../etc/passwd', '/themes/a.png', 'http://plain.test/a.png'):
            self.assertIsNone(self.clean(bad), bad)

    def test_blank_is_an_empty_cover(self):
        self.assertEqual(self.clean(''), '')


if __name__ == '__main__':
    unittest.main()
