"""The blog must not be a separate site.

It was one: server/blog.py carried its own copy of the header, the drawer, the
theme switch and the sun/moon icons - about half of that file - written out by
hand, once per language. The copies drifted exactly as copies do. The blog grew
a language <a> where the storefront has a <button>, lost the account button
entirely, and its theme button drew different glyphs. A visitor who clicked
"Blog" got a page that looked like the same site and did not behave like it.

The fix was to stop copying: the blog loads the storefront's own scripts now,
and app.js builds the header from one description that both pages use.

These tests are about the shape of that, because the shape is what regresses.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOG = (ROOT / 'server' / 'blog.py').read_text(encoding='utf-8')
APP = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')


def shell_source():
    start = BLOG.index('def shell(')
    end = BLOG.index('def _date(')
    return BLOG[start:end]


class OneHeaderTests(unittest.TestCase):
    def test_the_blog_loads_the_storefront_scripts(self):
        """The header only exists once these run; without them it is markup."""
        shell = shell_source()
        for script in ('i18n.js', 'icons.js', 'brands.js', 'app.js'):
            self.assertIn(script, shell,
                          f'the blog does not load {script}, so the shared '
                          'header cannot be built')

    def test_the_blog_does_not_rebuild_the_header_in_python(self):
        """A hand-written <header> here is the copy that drifts."""
        shell = shell_source()
        self.assertNotIn('<header class="topbar"', shell,
                         'the blog is drawing its own header again instead of '
                         'asking app.js for the shared one')

    def test_the_blog_does_not_rebuild_the_drawer_or_the_theme_switch(self):
        shell = shell_source()
        for marker in ('blog-mobile-nav', 'theme-toggle', 'blog-lang'):
            self.assertNotIn(marker, shell,
                             f'the blog re-implements {marker}, which app.js '
                             'already provides')

    def test_the_header_description_comes_from_one_function(self):
        self.assertIn('function headerHTML(', APP)
        self.assertIn('function mountHeader(', APP)
        # Both are exported for the server-rendered page, which cannot import.
        self.assertIn('mountHeader(', APP)
        self.assertIn("id=\"blog-header\"", APP + BLOG)


class NoPrivateStringTableTests(unittest.TestCase):
    def test_the_shared_header_uses_the_site_dictionary(self):
        """A second string table is how the two headers disagreed.

        The first version of headerHTML carried its own Persian, and its
        "About" read درباره ما while the storefront read دربارهٔ ما from the
        dictionary - one word, two spellings, one page apart.
        """
        start = APP.index('function headerHTML(')
        end = APP.index('function mountHeader(')
        body = APP[start:end]
        self.assertIn('AXIA_T', body,
                      'the shared header must read the site dictionary')
        self.assertNotIn('درباره', body,
                         'the shared header is carrying its own Persian again')


class ProductNamesStayLatinTests(unittest.TestCase):
    def test_aurion_is_not_transliterated(self):
        """AURION is a product name, like AXIASOFT. It keeps its own spelling."""
        i18n = (ROOT / 'public' / 'i18n.js').read_text(encoding='utf-8')
        self.assertIsNone(
            re.search(r"(['\"])AURION\1\s*:\s*['\"]اوریون['\"]", i18n),
            'AURION is transliterated in the dictionary; a product name is not a word')


class BlogPageBootTests(unittest.TestCase):
    def test_the_storefront_routing_is_skipped_on_the_blog(self):
        """app.js is shared, so everything that assumes #app must check."""
        self.assertIn('IS_SHOP', APP,
                      'app.js must know whether it is on the storefront before '
                      'rendering into #app, which the blog does not have')
        # The specific nodes that only the storefront has.
        for node in ("$('#year')", "$('#chat-launcher')"):
            guarded = re.search(
                re.escape(node) + r'.{0,40}(if\(|&&|\?)', APP, re.S)
            self.assertIsNotNone(guarded,
                                 f'{node} is used without checking it exists')


    def test_the_static_build_answers_the_api_on_article_pages(self):
        """The blog makes the same startup calls the storefront does.

        On GitHub Pages there is no Python server, so /api/site and /api/me
        have nothing to answer them. public/static-adapter.js is what fills
        that gap for the storefront; the blog pages were not getting it, so
        the account button and the site settings silently failed there while
        working on every other page. One site, one set of calls, one adapter.
        """
        build = (ROOT / 'tools' / 'build_static.py').read_text(encoding='utf-8')
        # Every place a blog page is written must pass through the adapter.
        writes = [i for i in range(len(build))
                  if build.startswith("blog.shell(", i)]
        self.assertTrue(writes, 'no blog.shell() call sites found')
        for at in writes:
            line_start = build.rfind('\n', 0, at)
            line = build[line_start:build.index('\n', at)]
            self.assertIn('inject_adapter', line,
                          f'a blog page is written without the static adapter: {line.strip()[:90]}')


if __name__ == '__main__':
    unittest.main()