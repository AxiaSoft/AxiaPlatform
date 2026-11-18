"""The drawers, after the window changes size.

Both drawers on this site are off-canvas panels that exist only at a narrow
width: the public header's menu below 820px, the admin sidebar below 760px.
Above that the CSS hides them and the layout shows the links in place.

Each one also does something to the page while it is open - the public menu
locks <body> so the page cannot scroll under a thumb, the admin drawer lays a
scrim over the console. Neither had any handling for the window changing size,
so a rotation left the state behind:

* the public menu stayed in the DOM, hidden by CSS, with <body> still locked -
  the page could not scroll, and because the button refuses to open a menu that
  is already there ("if($('.mobile-nav'))return") pressing it again did nothing.
  The menu was gone until a reload.
* the admin scrim stayed on top of a wide page and took every click, so the
  console looked frozen.

Those are the two reports behind "the drawers do not open".
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
ADMIN = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')
CSS = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')
ADMIN_CSS = (ROOT / 'public' / 'admin' / 'admin.css').read_text(encoding='utf-8')


def _drawer() -> str:
    """The public drawer's click handler, code only."""
    i = APP.index("mobileMenuButton.onclick=()=>{")
    return APP[i:APP.index("\nwindow.openAuth", i)]


class ThePublicMenuSurvivesAResize(unittest.TestCase):
    def test_it_closes_when_the_window_becomes_wide(self):
        body = _drawer()
        self.assertIn("addEventListener('resize',wideClose", body,
                      'the menu is never closed when the window becomes wide, '
                      'so it stays in the DOM with the page still locked')
        self.assertIn("addEventListener('orientationchange',wideClose", body)
        self.assertIn('window.innerWidth>820', body,
                      '820px is where styles.css stops drawing the menu')

    def test_closing_releases_the_page(self):
        """A stale lock is the visible half of the bug."""
        body = _drawer()
        close = body[body.index('const closeMenu'):]
        close = close[:close.index('};')]
        self.assertIn("document.body.style.overflow=''", close)

    def test_closing_resets_the_button(self):
        body = _drawer()
        close = body[body.index('const closeMenu'):]
        close = close[:close.index('};')]
        self.assertIn("setAttribute('aria-expanded','false')", close)

    def test_the_wide_close_does_not_steal_focus(self):
        """The button it would focus is hidden at that width."""
        body = _drawer()
        self.assertIn('closeMenu(false)', body)
        self.assertIn('if(refocus)mobileMenuButton.focus()', body)

    def test_the_listeners_do_not_pile_up(self):
        body = _drawer()
        close = body[body.index('const closeMenu'):]
        close = close[:close.index('};')]
        self.assertIn("removeEventListener('resize',wideClose)", close)
        self.assertIn("removeEventListener('orientationchange',wideClose)", close)

    def test_the_width_it_compares_against_is_the_one_the_css_uses(self):
        self.assertIn('@media(max-width:820px)', CSS)
        self.assertIn('.mobile-nav{display:flex!important', CSS)


class TheAdminSidebarSurvivesAResize(unittest.TestCase):
    def test_the_scrim_is_dropped_when_the_window_becomes_wide(self):
        self.assertIn('__axiaNavResize', ADMIN)
        i = ADMIN.index('__axiaNavResize=')
        body = ADMIN[i:i + 400]
        self.assertIn("classList.remove('open')", body)
        self.assertIn("classList.remove('show')", body)
        self.assertIn('window.innerWidth>760', body,
                      '760px is where admin.css stops drawing the drawer')

    def test_it_is_registered_once(self):
        self.assertIn('if(!window.__axiaNavResize)', ADMIN,
                      'shell() runs again on a language switch; the listener '
                      'must not be added twice')

    def test_the_width_it_compares_against_is_the_one_the_css_uses(self):
        self.assertIn('@media(max-width:760px)', ADMIN_CSS)
        self.assertIn('.sidebar.open{transform:translateX(0)}', ADMIN_CSS)


class TheOpenGuardCannotStrandTheMenu(unittest.TestCase):
    def test_the_guard_is_still_there(self):
        """It is correct - two menus at once would be a bug.

        The test exists to link it to this round: a menu left in the DOM makes
        this guard return early, which is how a stale menu became "the button
        does not work".
        """
        self.assertIn("if($('.mobile-nav'))return;", _drawer())


if __name__ == '__main__':
    unittest.main()
