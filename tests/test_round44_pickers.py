"""Every dropdown opens.

The console and the storefront draw their own listbox instead of a <select>:
a button with `data-picker-btn`, a list with the options, and a hidden input
that carries the value into the form. One click handler, registered on the
document, finds the list and toggles it.

It found it with `querySelector('[data-picker-list]')`. The template never
wrote that attribute - it wrote `class="picker-list"` - so the lookup returned
null, `togglePicker` bailed on its `if(!btn||!list)return;` guard, and *every*
dropdown on the site did nothing when pressed. The button still took the click
and still flipped `aria-expanded`, so it looked alive; only the list never
appeared.

The same two lines exist in both front ends, so the same mistake shipped twice:
"none of the dropdowns work in the admin panel" was the visible half.

A test never caught it because none of them read the template and the handler
together. These do: for each file, the element the template emits must be the
element the handler queries.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
ADMIN = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')

SOURCES = {'storefront': APP, 'admin': ADMIN}


def picker_template(src: str) -> str:
    """The `picker()` body that builds the markup."""
    i = src.index('function picker(')
    j = src.index('return `', i)
    return src[j:src.index('`;', j)]


def picker_handlers(src: str) -> str:
    """togglePicker and closePickers, where the list is looked up."""
    start = src.index('function closePickers')
    end = src.index('document.addEventListener', start)
    return src[start:end]


class TheTemplateAndTheHandlerAgree(unittest.TestCase):
    def test_the_list_the_template_writes_is_the_one_the_handler_finds(self):
        for name, src in SOURCES.items():
            with self.subTest(source=name):
                template = picker_template(src)
                handlers = picker_handlers(src)
                # What the markup writes...
                self.assertIn('data-picker-list', template,
                              f'{name}: the list element carries no '
                              f'data-picker-list, so the handler cannot find it')
                # ...must be what the handler asks for.
                self.assertIn("querySelector('[data-picker-list]')", handlers,
                              f'{name}: the handler does not query the '
                              f'attribute the template writes')

    def test_the_other_two_parts_already_agreed(self):
        """The button and the hidden input were always right.

        They are asserted here so a future rename cannot half-fix the trio.
        """
        for name, src in SOURCES.items():
            with self.subTest(source=name):
                template = picker_template(src)
                handlers = picker_handlers(src)
                self.assertIn('data-picker-btn', template)
                self.assertIn("querySelector('[data-picker-btn]')", handlers)
                self.assertIn('data-picker-input', template)

    def test_the_guard_cannot_silently_swallow_every_click(self):
        """`if(!btn||!list)return;` is what turned a wrong selector into
        a site-wide dead control: no error, no message, nothing."""
        for name, src in SOURCES.items():
            with self.subTest(source=name):
                handlers = picker_handlers(src)
                self.assertIn('if(!btn||!list)return;', handlers)
                # ...so the lookup above it must be right, which the first
                # test asserts. This one records why the guard matters.


class TheAdminPickersExistWhereTheConsoleDrawsThem(unittest.TestCase):
    """The console puts a picker on products, orders and settings.

    Rendering one and being able to open it are different things, and only the
    first was ever exercised.
    """

    def test_the_screens_that_offer_a_dropdown_still_do(self):
        for call in ("picker('product_filter'", "picker('product_sort'",
                     "picker('default_theme'", "picker('category_filter'"):
            with self.subTest(call=call):
                self.assertIn(call, ADMIN)

    def test_the_callback_names_are_defined(self):
        """A picker calls back by name - the markup is a string, so it cannot
        close over a function. A name with no definition fails silently."""
        names = set(re.findall(r"onPick:\s*'([A-Za-z_$][\w$]*)'", ADMIN))
        self.assertTrue(names, 'no picker declares a callback')
        for n in sorted(names):
            with self.subTest(callback=n):
                self.assertRegex(ADMIN, r'window\.' + re.escape(n) + r'\s*=',
                                 f'window.{n} is never defined, so choosing an '
                                 f'option does nothing')


if __name__ == '__main__':
    unittest.main()
