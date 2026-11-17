"""The icon set, and the button rules that go with it.

Two asks sit here. First, the site should use real icons rather than whatever
character was nearest on the keyboard - the header, the category cards, the
modal close buttons and the console sidebar all drew glyphs (↗ ⌘ ▣ ◈ ☰ ×) that
rendered at different weights and, in a right-to-left page, pointed the wrong
way. Second, no two buttons may touch, and buttons standing together should be
one size.

The tests below pin the mechanics rather than the taste: one source for the
icons, no glyphs left in the rendered markup, one height per tier, and a gap
that is not zero. Where the design is a judgement call the test records the
rule that was chosen and why.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The characters the site used to draw itself with. A template that still
# contains one of these is drawing an icon with a font.
GLYPHS = '\u2197\u25c8\u25a3\u2318\u2630\u00d7\u2713\u21bb\uff0b\u2699\u25a4\u2733\u21a9\u2659\u25f7\u25eb\u21e5\u25b2\u25bc'


class IconSetTests(unittest.TestCase):
    def setUp(self):
        self.icons = (ROOT / 'public' / 'icons.js').read_text(encoding='utf-8')

    def test_there_is_one_icon_file(self):
        self.assertIn('window.AXIA_ICON', self.icons)

    def test_every_page_loads_it_before_the_script_that_uses_it(self):
        for rel in ('public/index.html', 'public/admin/index.html'):
            html = (ROOT / rel).read_text(encoding='utf-8')
            self.assertIn('icons.js', html, f'{rel} does not load the icon set')
            self.assertLess(html.index('icons.js'), html.index('app.js' if 'admin' not in rel else 'admin/admin.js'),
                            f'{rel} loads the icon set after the code that calls it')

    def test_the_icons_are_one_family(self):
        # Same box, same stroke, no fill, currentColor - otherwise the set drifts
        # back into "several icons from several places".
        self.assertIn('viewBox="0 0 24 24"', self.icons)
        self.assertIn('stroke="currentColor"', self.icons)
        self.assertIn('fill="none"', self.icons)
        self.assertIn('stroke-linecap="round"', self.icons)
        self.assertIn('stroke-linejoin="round"', self.icons)
        # One stroke weight, declared once.
        self.assertEqual(len(re.findall(r'stroke-width="[\d.]+"', self.icons)), 1)

    def test_a_missing_name_returns_nothing_instead_of_undefined(self):
        # AXIA_ICON is called inside template literals. Returning undefined would
        # put the word "undefined" on the page; an empty string is invisible.
        self.assertIn('if (!d) return', self.icons)

    def test_every_icon_has_path_data(self):
        # A name in the map with an empty path draws a blank box, which is a
        # broken icon that no test would otherwise notice.
        body = self.icons[self.icons.index('var PATHS'):self.icons.index('window.AXIA_ICON')]
        self.assertNotIn(": '',", body)
        self.assertNotIn(': ""', body)


class NoGlyphsLeftTests(unittest.TestCase):
    """The rendered templates must not carry the old characters."""

    def test_the_storefront_templates_have_no_glyph_icons(self):
        app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        found = sorted({ch for ch in GLYPHS if ch in app})
        self.assertEqual(found, [], 'these are still drawn with a font')

    def test_the_console_templates_have_no_glyph_icons(self):
        admin = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')
        # The comment block explains what was removed and names the characters,
        # so it is excluded rather than allowed to fail the scan.
        body = re.sub(r'/\*.*?\*/', '', admin, flags=re.S)
        found = sorted({ch for ch in GLYPHS if ch in body})
        self.assertEqual(found, [], 'these are still drawn with a font')

    def test_the_shell_has_no_glyph_icons(self):
        for rel in ('public/index.html', 'public/admin/index.html'):
            html = (ROOT / rel).read_text(encoding='utf-8')
            found = sorted({ch for ch in GLYPHS if ch in html})
            self.assertEqual(found, [], f'{rel} still draws {found}')

    def test_a_dictionary_key_never_contains_an_icon_glyph(self):
        # T() looks up its argument exactly. A key ending in a glyph stops
        # matching the moment the glyph becomes an icon, and the translation
        # goes silently back to English - which is what happened to
        # 'Open my conversations ↗'.
        i18n = (ROOT / 'public' / 'i18n.js').read_text(encoding='utf-8')
        keys = re.findall(r"'([^'\n]{1,120})'\s*:", i18n)
        offenders = [k for k in keys if any(ch in GLYPHS for ch in k)]
        self.assertEqual(offenders, [], 'these keys can never match their text')


class IconAccessibilityTests(unittest.TestCase):
    """An icon is not a label.

    Every icon in the set is aria-hidden, so a screen reader reads the button's
    text or its aria-label - never the name of a drawing. That is only safe if
    each icon-only control actually has one of those, which is what this checks.
    """

    def setUp(self):
        self.shell = (ROOT / 'public' / 'index.html').read_text(encoding='utf-8')
        self.icons = (ROOT / 'public' / 'icons.js').read_text(encoding='utf-8')

    def test_every_icon_is_hidden_from_assistive_technology(self):
        self.assertIn('aria-hidden="true"', self.icons)
        self.assertIn('focusable="false"', self.icons)

    def test_every_icon_only_button_in_the_shell_has_a_name(self):
        # The theme toggle and the menu button draw no text, so the accessible
        # name has to come from aria-label.
        for cls in ('theme-toggle', 'mobile-menu'):
            i = self.shell.index(cls)
            tag = self.shell[self.shell.rfind('<', 0, i):self.shell.index('>', i)]
            self.assertIn('aria-label=', tag, f'{cls} has no accessible name')

    def test_the_menu_button_does_not_point_at_an_id_that_appears_later(self):
        # The drawer is created on the first press, so aria-controls="mobileNav"
        # named an element the accessibility tree cannot find until then.
        i = self.shell.index('id="mobileMenuButton"')
        tag = self.shell[self.shell.rfind('<', 0, i):self.shell.index('>', i)]
        self.assertNotIn('aria-controls', tag)
        self.assertIn('aria-haspopup="true"', tag)

    def test_a_movement_icon_is_flipped_in_the_right_to_left_page(self):
        # An arrow pointing right means "forward" in a Latin page and "back" in
        # a Persian one. The page is RTL, so the icon flips.
        css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')
        self.assertRegex(css, r'\[dir="rtl"\] \.dir-icon\s*\{\s*transform:\s*scaleX\(-1\)')


class ButtonRuleTests(unittest.TestCase):
    """One height per tier, and never zero gap between two buttons."""

    def setUp(self):
        self.css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')
        self.admin = (ROOT / 'public' / 'admin' / 'admin.css').read_text(encoding='utf-8')

    def test_button_height_is_a_variable_not_a_literal(self):
        # It used to be 42 in one rule, 38 in another, 37, 36 and unset. One
        # variable is what makes "the same size" true rather than asserted.
        self.assertIn('--btn-h', self.css)
        self.assertIn('--btn-h-sm', self.css)
        self.assertRegex(self.css, r'\.button\s*\{[^}]*min-height:\s*var\(--btn-h\)')

    def test_an_icon_button_is_square_and_the_same_height(self):
        # The first .icon-button rule sets the square shape; a later one pins the
        # header tier. Both must take their size from the variable.
        blocks = [b for b in re.findall(r'\.icon-button\s*\{([^}]*)\}', self.css)
                  if 'width' in b or 'height' in b]
        self.assertTrue(blocks, 'no .icon-button rule found')
        for block in blocks:
            self.assertIn('var(--btn-h', block.replace(' ', ''), block)

    def test_the_header_uses_one_tier_for_all_its_controls(self):
        # The theme toggle and the menu are square icon buttons; the sign-in
        # control is a text button. They shared a row but not a height.
        self.assertRegex(self.css, r'\.nav-actions[^{]*\{[^}]*--btn-h:\s*var\(--btn-h-sm\)')

    def test_button_gaps_are_a_variable_and_not_zero(self):
        self.assertIn('--btn-gap', self.css)
        value = re.search(r'--btn-gap:\s*(\d+)px', self.css)
        self.assertIsNotNone(value)
        self.assertGreater(int(value.group(1)), 0, 'buttons must not touch')

    def test_the_shrinking_overrides_are_gone(self):
        # These were the rules that made one button 9px type and another 13px.
        for gone in ('.product-actions .button{padding:9px 6px',
                     '.package .button{font-size:10px;padding:9px 7px}',
                     '.nav-actions .button-small{padding:7px 8px'):
            self.assertNotIn(gone, self.css, f'{gone} still shrinks a button')

    def test_a_row_of_buttons_does_not_stretch_one_to_fill_it(self):
        # A stretched button beside a natural-width one reads as a different
        # control, which is the "not the same size" complaint.
        self.assertNotIn('.hero-actions .button{flex:1', self.css)
        self.assertNotIn('.hero-actions{align-items:stretch}', self.css)

    def test_the_console_has_the_same_two_variables(self):
        self.assertIn('--btn-h', self.admin)
        self.assertIn('--btn-gap', self.admin)

    def test_no_console_row_keeps_the_six_pixel_gap(self):
        self.assertRegex(self.admin, r'\.row-actions[^{]*\{[^}]*gap:\s*var\(--btn-gap\)')


if __name__ == '__main__':
    unittest.main()
