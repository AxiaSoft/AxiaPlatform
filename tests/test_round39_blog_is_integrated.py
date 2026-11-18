"""The blog is part of the site, not a page that merely looks like it.

Round 38 shared the header's *markup*: the blog and the storefront drew the
same buttons. They were not the same site, because the markup was all that
was shared. The three things a visitor actually does on a page - press Sign
in, switch the theme, read the nav the administrator configured - all failed
on the blog while working on the storefront, and none of those failures show
up in a diff of the HTML they render.

Each bug below had the same shape: a control was found and bound once, at
load time, to whatever element existed at that moment. On the storefront the
header is in index.html, so that worked. On the blog the header is injected
by app.js after it starts, so there was nothing to bind to yet, and the code
guarded itself with `if (button)` and carried on. The button was drawn,
looked correct, and did nothing. These tests assert the shape that survives
either order, not the specific line numbers.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
I18N = (ROOT / 'public' / 'i18n.js').read_text(encoding='utf-8')


class SignInWorksOnEveryPage(unittest.TestCase):
    """Every dialog is drawn into #modal-root.

    The storefront declares that element. A server-rendered page does not,
    and `modalRoot.innerHTML = ...` on null throws before anything is drawn -
    or, where it was guarded, does nothing visible. Pressing Sign in on an
    article page ran the handler and produced no dialog at all.
    """

    def test_the_modal_host_is_created_when_a_page_has_none(self):
        self.assertIn("document.querySelector('#modal-root')||", APP,
                      'the modal host is assumed to exist again')
        self.assertIn("node.id='modal-root'", APP)

    def test_it_falls_back_to_a_document_that_still_has_no_body(self):
        # app.js is deferred today, so <body> exists; a page that ever loads it
        # without defer would otherwise throw on the first line.
        self.assertIn('document.body||document.documentElement', APP)

    def test_the_dialog_is_still_wired_to_the_account_button(self):
        # The handler's shape is a matter for test_round42_account_button; what
        # this round is guarding is that signing out still reaches the dialog.
        i = APP.index("$('#accountButton')")
        self.assertIn('openAuth()', APP[i:APP.index('\nfunction ', i)],
                      'the account button no longer opens the sign-in dialog')


class TheThemeSwitchWorksEverywhere(unittest.TestCase):
    """The switch listens on the document, not on one button instance."""

    def test_the_theme_switch_is_delegated(self):
        self.assertIn("event.target.closest('.theme-toggle')", APP,
                      'the theme switch is bound to one element again, so it '
                      'stops working on any page whose header is built later')
        self.assertIn("addEventListener('click', event =>", APP)

    def test_it_still_persists_the_choice(self):
        self.assertIn("localStorage.setItem('axia-theme', next)", APP)

    def test_the_old_load_time_binding_is_gone(self):
        # The exact statement that broke the blog: query once, bind once.
        self.assertNotIn("const _tt=$('.theme-toggle')", APP)

    def test_the_language_switch_is_delegated_too(self):
        self.assertIn("event.target.closest('#languageToggle')", I18N,
                      'the language switch is bound at load again, so an '
                      'English blog cannot be switched from')
        self.assertNotIn("const toggle=document.querySelector('#languageToggle')",
                         I18N)


class TheNavObeysTheSettingsOnBothPages(unittest.TestCase):
    """A link is identified by its route, not by the string it was written as.

    The storefront writes "#/products". The blog's header carries the
    deployment path in front of it - "/#/products", or "/AxiaPlatform/#/products"
    when published under a sub-path. A table keyed by the whole href matched
    none of the blog's links, so the blog kept showing sections an
    administrator had switched off.
    """

    def test_the_visibility_table_is_keyed_by_route(self):
        for route, flag in (("'/products':'show_catalog'", 'catalog'),
                            ("'/services':'show_services'", 'services'),
                            ("'/aurion':'show_aurion'", 'aurion'),
                            ("'/about':'show_about'", 'about')):
            self.assertIn(route, APP, f'the {flag} switch is not mapped to a route')

    def test_the_base_path_is_stripped_before_the_lookup(self):
        self.assertIn("href.slice(href.indexOf('#/') + 1)", APP,
                      'links are matched on their literal href again')

    def test_the_blog_header_spec_uses_a_base_path(self):
        """Guard the reason the route lookup exists.

        If the blog ever stops prefixing its links, this test still passes and
        the lookup is merely harmless; if it starts using a different form,
        the shared lookup above is what keeps the two pages agreeing.
        """
        import sys
        sys.path.insert(0, str(ROOT / 'server'))
        import blog
        shell = blog.shell(head='', body='x', lang='fa', base='',
                           default_theme='dark')
        self.assertIn('id="blog-header"', shell)
        self.assertIn('"products"', shell)


class TheFooterIsSharedToo(unittest.TestCase):
    """The footer was the third copy of the chrome, and nobody noticed.

    It was hand-written in blog.py: three links instead of the storefront's
    four, "© AXIASOFT" with no year, and the tagline from blog.py's own table.
    The header was shared last round and the page still read as a different
    site, because the bottom of it was not.
    """

    def test_the_blog_does_not_write_its_own_footer(self):
        blog = (ROOT / 'server' / 'blog.py').read_text(encoding='utf-8')
        self.assertNotIn('<footer class="footer">', blog,
                         'the blog is drawing a footer again')

    def test_the_footer_has_one_build_function(self):
        self.assertIn('function footerHTML(', APP)
        self.assertIn('function mountFooter(', APP)
        # The same destinations the storefront's footer carries.
        for key in ('privacy', 'terms', 'refunds-policy', 'contact'):
            self.assertIn(f"['{key}'", APP, f'the shared footer has no {key} link')

    def test_the_shared_footer_carries_the_year(self):
        # The blog's copy read "© AXIASOFT" with no year in it.
        self.assertIn('<span id="year">', APP)

    def test_the_blog_page_mounts_the_shared_footer(self):
        self.assertIn('mountFooter({lang: opts.lang, href})', APP)


class TheBlogReadsTheRealSiteSettings(unittest.TestCase):
    """An article page was rendering the shipped design, not the live one.

    The static adapter answers /api/site and /api/products from the snapshot
    that static-config.js, data/settings.js and data/products.js put on
    window.AXIA_STATIC. The storefront has always loaded those three; the
    blog's shell did not, so its adapter fell back to built-in defaults and
    kept its own idea of the footer note, the hero and which sections exist.
    """

    def test_the_build_gives_article_pages_the_snapshot(self):
        build = (ROOT / 'tools' / 'build_static.py').read_text(encoding='utf-8')
        self.assertIn('def inject_snapshot(', build)
        for name in ('static-config.js', 'data/settings.js', 'data/products.js'):
            self.assertIn(name, build)
        # Every blog write site goes through it, like the adapter.
        self.assertEqual(build.count('inject_snapshot(inject_adapter('), 3)

    def test_the_live_server_does_not_link_to_files_it_does_not_serve(self):
        """Those three paths 404 on the server build, and correctly.

        The server answers /api/site from the database. Linking the tags
        unconditionally would put three failing requests in every article
        page's console, so the injection belongs to the static build only.
        """
        blog = (ROOT / 'server' / 'blog.py').read_text(encoding='utf-8')
        self.assertNotIn('static-config.js', blog)


if __name__ == '__main__':
    unittest.main()