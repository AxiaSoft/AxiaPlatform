"""The drawer, the language switch and the dialogs, on every page.

Round 39 made the blog and the storefront share a header. This round is the
controls that header hangs off, and the ones that were never shared at all.

Every bug here had the same cause as the last three rounds: the same question
answered in two places. Where a route is spelled. Which menu items are
switched on. Which language the page is in. Each was answered once for the
storefront and once - differently - for the blog.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
I18N = (ROOT / 'public' / 'i18n.js').read_text(encoding='utf-8')


class TheMenuAndTheHeaderAgree(unittest.TestCase):
    """The phone menu hides exactly what the header hides.

    The drawer listed every destination and let applyChrome hide the ones it
    recognised by href - and it did not recognise the drawer's, because the
    drawer builds them ("#/products") while the header on the blog writes
    them with the site root in front ("/#/products"). So a phone offered
    Services on a site whose Services page is switched off, while the desktop
    header next to it did not.
    """

    def test_there_is_one_route_to_flag_table(self):
        self.assertEqual(APP.count('const NAV_FLAGS='), 1,
                         'the visibility map is declared more than once again')
        start = APP.index('const NAV_FLAGS=')
        table = APP[start:APP.index('};', start)]
        for route in ('/products', '/services', '/aurion', '/about'):
            self.assertIn(f"'{route}'", table, f'{route} has no switch')

    def test_the_drawer_filters_by_that_table(self):
        start = APP.index("mobileMenuButton=$('.mobile-menu')")
        drawer = APP[start:APP.index('window.openAuth=openAuth;', start)]
        self.assertIn('NAV_FLAGS', drawer,
                      'the drawer is drawing switched-off sections again')
        self.assertIn('NAV_ORDER_MENU.filter', drawer)

    def test_the_drawer_reads_the_header_s_destinations(self):
        """One source of truth for how a route is spelled on this page.

        The drawer used to build "#/products" itself. On an article page that
        resolves to "/blog/#/products", which is not a page - so the menu
        looked right and every link in it went nowhere.
        """
        start = APP.index("mobileMenuButton=$('.mobile-menu')")
        drawer = APP[start:APP.index('window.openAuth=openAuth;', start)]
        self.assertIn('window.AXIA_NAV', drawer,
                      'the drawer is building hrefs instead of using the '
                      "header's")
        self.assertIn('window.AXIA_NAV', APP)
        # and the header publishes it
        header = APP[APP.index('function headerHTML('):APP.index('function mountHeader(')]
        self.assertIn('window.AXIA_NAV', header)

    def test_the_blog_destination_keeps_the_deploy_base(self):
        # /blog/ is a real directory; a raw one 404s under a sub-path.
        self.assertIn("assetUrl('blog/'", APP)


class TheLanguageSwitchChangesTheLanguage(unittest.TestCase):
    """A stored choice has to be able to beat the page's static default.

    The storefront's index.html carries <html lang="fa" dir="rtl"> so the page
    can paint right-to-left before any script runs. i18n.js read that as "the
    page declares Persian" and let it win over localStorage every time, so
    the switch wrote the preference, reloaded, and came back Persian. That was
    introduced by round 38's fix for the English blog.
    """

    def test_a_static_lang_attribute_is_not_a_declaration(self):
        self.assertIn('serverDeclared', I18N)
        self.assertIn("document.getElementById('blog-header')", I18N,
                      'the declared-language rule is not limited to pages the '
                      'server wrote in a language')

    def test_the_stored_choice_is_still_read(self):
        self.assertIn("localStorage.getItem('axia-lang')", I18N)

    def test_the_blog_switch_navigates_to_the_other_language(self):
        # /blog/ is Persian by address; reloading it cannot make it English.
        self.assertIn('otherLangUrl', I18N)
        self.assertIn('location.assign(target)', I18N)

    def test_the_server_sends_that_url(self):
        blog = (ROOT / 'server' / 'blog.py').read_text(encoding='utf-8')
        self.assertIn("'otherLangUrl': other_lang_url", blog)

    def test_the_switch_button_says_the_same_thing_on_both_pages(self):
        """It read "EN" on the storefront and "English" on the blog."""
        self.assertNotIn("'English'}</button>", APP)
        self.assertIn("'فارسی' : 'EN'", APP)


class TheDialogsAreInOneLanguage(unittest.TestCase):
    """A confirmation showed English sentences and Persian buttons.

    confirmDialog is handed its text by the caller, in English, and the site
    translates text nodes as they appear. The strings it was given were not in
    the dictionary, so the sentences stayed English while the surrounding
    chrome was Persian.
    """

    CONFIRM_STRINGS = (
        'Sign out?',
        'Stay signed in',
        'Your session ends on this device. You can sign back in any time.',
        'Your session ends on this device. Your projects, messages and requests '
        'stay on your account, and you can sign back in any time.',
    )

    def test_every_confirmation_string_is_in_the_dictionary(self):
        for text in self.CONFIRM_STRINGS:
            self.assertIn(f"'{text}'", I18N, f'the dictionary has no {text!r}')

    def test_the_cancel_button_reads_as_a_refusal(self):
        # "بمانید واردشده" was a literal calque of "Stay signed in".
        self.assertIn("'Stay signed in':'انصراف'", I18N)

    def test_the_dictionary_has_no_untranslated_confirmation_left(self):
        """A Persian sentence must not carry a Latin sentence inside it."""
        m = re.search(r"'Stay signed in':'([^']*)'", I18N)
        self.assertIsNotNone(m)
        self.assertFalse(re.search(r'[A-Za-z]{3,}', m.group(1)),
                         'the Persian is still half English')


class TheHeaderIsTheSameHeader(unittest.TestCase):
    """The markup both pages draw, from the one function that draws it.

    A phone renders the CTA arrow from this file and the storefront renders
    its own from index.html; they had different stroke widths and different
    glyphs, which reads as two products side by side.
    """

    def test_the_two_headers_draw_the_same_cta_arrow(self):
        index = (ROOT / 'public' / 'index.html').read_text(encoding='utf-8')
        header = APP[APP.index('function headerHTML('):APP.index('function mountHeader(')]
        for markup in (index, header):
            self.assertIn('M7 17 17 7M9 7h8v8', markup,
                          'the CTA arrow differs between the two headers')
            self.assertIn('stroke-width="1.75"', markup,
                          'the header icons are drawn at two weights')

    def test_the_language_button_carries_a_title_everywhere(self):
        header = APP[APP.index('function headerHTML('):APP.index('function mountHeader(')]
        self.assertRegex(header, r'language-toggle[^>]*title=',
                         'the blog\'s language button has no tooltip')


if __name__ == '__main__':
    unittest.main()
