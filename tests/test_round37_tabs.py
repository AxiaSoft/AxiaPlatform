"""The website tabs have to lead somewhere.

Two of the seven tabs on the console's Website page - Questions and Site
brands - had their markup written (faqTabHTML, brandsTabHTML) and were never
routed to. siteTabHTML() is an if-chain ending in an unconditional return for
the identity form, so a tab without a branch above that line does not error: it
quietly shows the identity form instead. Choosing "Questions" and getting the
identity form looks exactly like a broken console, and nothing failed.

These assertions are about that line, because that is where the bug was.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONSOLE = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')


def site_tab_body(source):
    start = source.index('function siteTabHTML(){')
    end = source.index('function visibleSetting')
    return source[start:end]


class WebsiteTabTests(unittest.TestCase):
    def test_every_tab_button_has_a_branch(self):
        """A tab in the tab bar with no branch is a tab that lies."""
        tabs = re.search(r'const SITE_TABS=\[(.*?)\];', CONSOLE, re.S).group(1)
        ids = re.findall(r"\['(\w+)'", tabs)
        self.assertGreaterEqual(len(ids), 7)
        body = site_tab_body(CONSOLE)
        branches = set(re.findall(r"t===?'(\w+)'", body))
        # identity is the fallthrough, not a branch.
        missing = [i for i in ids if i != 'identity' and i not in branches]
        self.assertEqual(missing, [], f'tabs with no branch: {missing}')

    def test_the_extra_branches_precede_the_fallthrough(self):
        """Above the identity return, or they can never run.

        This is the whole bug: the branches were appended after an
        unconditional return, so the code was unreachable rather than absent.
        """
        body = site_tab_body(CONSOLE)
        fallthrough = body.index('Site identity')
        for name in ('brands', 'faq'):
            branch = body.index(f"t==='{name}'")
            self.assertLess(branch, fallthrough,
                            f"the {name} branch sits below the identity "
                            "fallthrough and can never be reached")

    def test_the_tab_functions_called_actually_exist(self):
        body = site_tab_body(CONSOLE)
        for called in re.findall(r'return (\w+TabHTML)\(\)', body):
            self.assertIn(f'function {called}(', CONSOLE,
                          f'{called} is called but never defined')


class GlyphTests(unittest.TestCase):
    def test_the_reorder_buttons_are_icons_not_characters(self):
        """A button whose label is an arrow character depends on the font.

        The product, category, brand and question rows all reorder the same
        way. Two of the four drew a literal up/down arrow, so the same control
        looked different on the same screen.
        """
        for action in ('move-product', 'move-category', 'brand-up', 'brand-down',
                       'faq-up', 'faq-down'):
            found = re.search(
                r'data-act="' + action + r'"[^>]*>([^<]*)</button>', CONSOLE)
            self.assertIsNotNone(found, f'{action} button not found')
            inner = found.group(1).strip()
            self.assertNotIn(inner, ('\u2191', '\u2193'),
                             f'{action} still draws an arrow character')


if __name__ == '__main__':
    unittest.main()
