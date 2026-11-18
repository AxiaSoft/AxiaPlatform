"""The account button, pressed on the blog.

Signed out it opened the sign-in dialog, because that dialog is drawn into the
document you are already on. Signed in it went nowhere: the handler called

    go('/account')            ->  location.hash = '#/account'

and location.hash is a route *into the current document*. On the storefront
that is the account page. On the blog it is /blog/#/account, a URL that was
never built, so the page did not change, no error was raised, and the visitor
was left looking at the article. The admin branch had the sister fault -
location.assign('/admin/') is absolute at the domain root, so under the
/AxiaPlatform/ deploy base it left the site altogether.

Both destinations live on the storefront. They have to be written as the
storefront's address, from whichever page the button is pressed.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')


def _strip_comments(src: str) -> str:
    """Comments quote the code that was there; assertions are about the code."""
    return re.sub(r'/\*.*?\*/', '', src, flags=re.S)


def account_handler() -> str:
    """The account button's click handler, code only, as written in app.js.

    Sliced to the next top-level declaration rather than to matching braces:
    the point of these tests is to read whatever is there, including a shape
    the fixed version does not have.
    """
    i = APP.index("$('#accountButton')")
    j = APP.index('onclick', i)
    body = APP[j:]
    for stop in ('\nfunction ', '\nconst ', '\nlet ', '\n/* '):
        k = body.find(stop)
        if k != -1:
            body = body[:k]
    return _strip_comments(body).strip()


class TheAccountButtonLeavesTheBlog(unittest.TestCase):
    def test_it_does_not_set_a_hash_on_the_current_document(self):
        """The root cause, directly.

        go() is location.hash, a route into the document you are on. It is a
        correct way to reach the account page from the storefront and a dead
        end from anywhere else, so it may only appear behind the storefront
        check.
        """
        handler = account_handler()
        self.assertNotIn('location.hash', handler)
        if "go('/account')" in handler:
            call = handler.index("go('/account')")
            guards = [g for g in ('if(IS_SHOP)', 'IS_SHOP&&', 'IS_SHOP ?') if g in handler]
            self.assertTrue(guards, 'the hash route must be guarded by IS_SHOP')
            self.assertLess(handler.index(guards[0]), call,
                            'the hash route must be guarded by IS_SHOP')

    def test_the_customer_destination_is_the_storefront_account_page(self):
        handler = account_handler()
        self.assertIn("#/account", handler)
        # ...prefixed by the site root, not by nothing.
        self.assertRegex(handler, r"assetUrl\(\s*''\s*\)\s*\+\s*'#/account'")

    def test_off_the_storefront_it_never_uses_the_hash_of_this_page(self):
        """IS_SHOP is the discriminator, and it is !!#app.

        The blog has no #app, so on the blog IS_SHOP is false and the code
        that runs is the one that starts from the site root.
        """
        handler = account_handler()
        self.assertIn('if(IS_SHOP)', handler)
        decl = _strip_comments(APP)
        decl = decl[decl.index('const IS_SHOP'):]
        decl = decl[:decl.index(';')]
        self.assertIn('#app', decl, 'IS_SHOP is what tells the two documents apart')
        # The unguarded navigation in this handler is the absolute one.
        self.assertRegex(handler, r"location\.assign\(assetUrl\(\s*''\s*\)\s*\+\s*'#/account'\)")

    def test_the_admin_destination_survives_the_deploy_base(self):
        """location.assign('/admin/') is absolute at the domain root.

        That is wrong for a site published under /AxiaPlatform/: it points at
        the domain root's admin page, which is not ours.
        """
        handler = account_handler()
        self.assertIn("assetUrl('admin/')", handler)
        self.assertNotIn("location.assign('/admin/')", handler)

    def test_signed_out_still_opens_the_dialog(self):
        handler = account_handler()
        self.assertIn('if(!me)return openAuth()', handler)

    def test_the_handler_does_not_navigate_signed_out(self):
        """A visitor with no session gets the dialog, not a page load."""
        handler = account_handler()
        head, _, _ = handler.partition('openAuth()')
        self.assertNotIn('location.assign', head)


class TheSiteRootIsWhereItSaysItIs(unittest.TestCase):
    """assetUrl('') is the storefront root on every page.

    The handler leans on it, so the fallbacks it can reach must all be right.
    """

    def test_it_strips_the_blog_and_admin_paths(self):
        body = APP[APP.index('function assetUrl'):]
        body = body[:body.index('\n}')]
        self.assertIn("'/blog/'", body, 'the blog sub-path is recognised')
        self.assertIn("'/admin/'", body, 'the admin sub-path is recognised')
        self.assertIn("'/' + clean", body, 'and the plain root is returned')


class NothingElseInTheHeaderUsesAHуshRoute(unittest.TestCase):
    """The nav links on the blog already spell the root out.

    The account button was the one control that did not, and this test pins
    the pattern it was brought into line with, so a later edit that reverts
    to a bare hash is caught.
    """

    def test_nav_destination_is_root_prefixed(self):
        body = APP[APP.index('const navDestination='):]
        body = body[:body.index(';')]
        self.assertIn("assetUrl", body)


if __name__ == '__main__':
    unittest.main()
