"""Guards for the generated GitHub Pages build.

The static build has no server, so a single malformed tag in the shell can
disable it silently: an unclosed <script> swallows every following tag as raw
text, which is exactly how the static adapter once disappeared from a build
that still reported success. These tests fail loudly instead.
"""
import sys
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('build_static', ROOT / 'tools' / 'build_static.py')
build_static = module_from_spec(spec)
spec.loader.exec_module(build_static)


class UnclosedScriptTests(unittest.TestCase):
    def test_detects_a_tag_that_is_never_closed(self):
        html = '<script src="a.js" defer>\n<script src="b.js"></script>'
        self.assertEqual(build_static.unclosed_scripts(html), ['a.js'])

    def test_accepts_well_formed_tags(self):
        html = '<script src="a.js" defer></script>\n<script src="b.js"></script>'
        self.assertEqual(build_static.unclosed_scripts(html), [])

    def test_ignores_inline_scripts_without_src(self):
        html = '<script>var a = 1;</script>\n<script src="b.js"></script>'
        self.assertEqual(build_static.unclosed_scripts(html), [])

    def test_public_shell_has_no_unclosed_tags(self):
        for page in sorted((ROOT / 'public').rglob('*.html')):
            with self.subTest(page=page.name):
                html = page.read_text(encoding='utf-8')
                self.assertEqual(build_static.unclosed_scripts(html), [])


class ShellBundleOrderTests(unittest.TestCase):
    """Every bundle the shell declares must actually run in the browser."""

    def setUp(self):
        self.html = (ROOT / 'public' / 'index.html').read_text(encoding='utf-8')

    def test_static_adapter_is_loaded_before_the_app(self):
        html = build_static.inject_adapter(self.html, '/AxiaPlatform/')
        adapter = html.index('static-adapter.js')
        app = html.index('app.js?v=')
        self.assertLess(adapter, app, 'the adapter must install before the app boots')

    def test_brand_layer_loads_before_the_app(self):
        # applyBrand() reads window.AXIA_BRANDS, which brands.js defines.
        self.assertLess(self.html.index('brands.js'), self.html.index('app.js?v='))

    def test_injection_is_idempotent(self):
        once = build_static.inject_adapter(self.html, '/AxiaPlatform/')
        twice = build_static.inject_adapter(once, '/AxiaPlatform/')
        self.assertEqual(once, twice)


class CoverPathTests(unittest.TestCase):
    """Product covers are stored root-absolute; a sub-path build must rewrite them."""

    def test_prefix_is_applied_verbatim(self):
        base = '/AxiaPlatform/'
        cover = '/brand/arya-logo.png'
        self.assertEqual(base.rstrip('/') + cover, '/AxiaPlatform/brand/arya-logo.png')

    def test_prefixing_twice_never_doubles_the_base(self):
        # The published build is committed to the repo root and rebuilt in
        # place, so the prefix step must be safe to run on its own output.
        # Otherwise covers become /AxiaPlatform/AxiaPlatform/brand/... and every
        # product image 404s - which is exactly what happened once.
        base = '/AxiaPlatform/'
        prefix = base.rstrip('/')
        cover = '/brand/arya-logo.png'
        once = prefix + cover
        twice = once if once.startswith(prefix + '/') else prefix + once
        self.assertEqual(twice, '/AxiaPlatform/brand/arya-logo.png')
        self.assertEqual(twice.count('/AxiaPlatform'), 1)

    def test_published_catalog_covers_carry_the_prefix_exactly_once(self):
        # data/products.json is a build output that is committed at the repo
        # root, so the published copy legitimately carries the prefix. What must
        # never happen is the prefix stacking up on a rebuild.
        import json
        data = json.loads((ROOT / 'data' / 'products.json').read_text(encoding='utf-8'))
        for product in data:
            cover = product.get('cover') or ''
            if cover:
                self.assertTrue(cover.startswith('/'), f'{product["slug"]} cover must be root-absolute')
                self.assertLessEqual(cover.count('/AxiaPlatform/'), 1,
                                     f'{product["slug"]} cover has a doubled base prefix: {cover}')


if __name__ == '__main__':
    unittest.main()


class ProductCoverArtTests(unittest.TestCase):
    """The card art must show the whole uploaded image, at one size.

    The product covers are square logos (about 418x420) in a wide, short box.
    object-fit: cover scaled a square until its width filled the box, which threw
    away just over half the logo's height - the mark was sliced through the
    middle and the brand name underneath vanished. object-fit: contain fits the
    whole image, so nothing is cropped; the box is tall enough that every card
    shows its logo at the same height.
    """

    @classmethod
    def setUpClass(cls):
        cls.css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')
        cls.built = (ROOT / 'styles.css').read_text(encoding='utf-8')

    def _rule(self, css, selector):
        # Match the rule that starts with this selector exactly: searching for
        # the substring also finds '.detail-visual .product-cover...', which
        # overrides only the padding.
        start = 0
        while True:
            start = css.index(selector, start)
            if start == 0 or css[start - 1] in '{}\n':
                break
            start += len(selector)
        return css[start:css.index('}', start)]

    def test_the_cover_is_contained_not_cropped(self):
        for name, css in (('public', self.css), ('built root', self.built)):
            rule = self._rule(css, '.product-cover.has-image img')
            self.assertIn('object-fit: contain', rule,
                          f'{name}: an uploaded cover must not be cropped')
            self.assertNotIn('object-fit: cover', rule, name)

    def test_every_card_box_is_the_same_height(self):
        for name, css in (('public', self.css), ('built root', self.built)):
            rule = self._rule(css, '.product-cover.has-image {')
            self.assertIn('height:', rule,
                          f'{name}: uploaded covers need their own fixed height, '
                          'or a row of cards stops lining up')
            self.assertIn('232px', rule, name)

    def test_one_cover_height_everywhere(self):
        # A mobile override lived in the media query near the top of the file,
        # but the base .has-image rule comes later at equal specificity, so the
        # override never applied. Rather than keep a rule that does nothing,
        # the box has a single height and the card gets narrower on a phone,
        # not shorter - which keeps the logo the same size on both.
        import re
        for name, css in (('public', self.css), ('built root', self.built)):
            heights = re.findall(
                r'\.product-cover\.has-image\s*\{[^}]*height:\s*(\d+)px', css)
            self.assertEqual(sorted(set(heights)), ['232'], name)

    def test_the_label_does_not_stretch_across_the_card(self):
        # The cover is a grid with place-items:center, which stretched a
        # positioned child to its inset box: the label spanned 334 of 360px and
        # read as an empty bar.
        rule = self._rule(self.css, '.product-cover.has-image .cover-label')
        self.assertIn('width: max-content', rule)


class HomeLayoutTests(unittest.TestCase):
    """The home page's shape, pinned down after a round of restructuring.

    Three changes landed together and each one has a way of silently coming
    back:

      * the "Our north star" card was removed from the about block,
      * the landing strip ("Digital, with intention.") moved above the
        "Independent thinking. Intentional engineering." line,
      * the AXIASOFT mark moved from the hero's right column to a section of its
        own, under that landing strip.

    Reordering is not the kind of thing a screenshot keeps honest over time, so
    the order is asserted against the markup that actually ships.
    """

    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        cls.built = (ROOT / 'app.js').read_text(encoding='utf-8')
        cls.css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')

    def _home(self, js):
        # home() is the template literal that returns the whole page.
        start = js.index('function home(){')
        end = js.index('function productArt(', start)
        return js[start:end]

    def test_the_north_star_card_is_gone(self):
        for name, js in (('public', self.js), ('built root', self.built)):
            home = self._home(js)
            self.assertNotIn('Our north star', home,
                             f'{name}: the north-star card was removed from the home page')
            self.assertNotIn('feature-panel', home,
                             f'{name}: its empty column must not remain either')

    def test_the_section_that_held_it_is_no_longer_half_empty(self):
        # With the card gone the about block kept a two-column grid whose second
        # column had nothing in it, leaving half the page blank.
        home = self._home(self.js)
        self.assertIn('two-col-single', home)
        self.assertIn('.two-col-single', self.css)

    def test_the_landing_comes_before_the_independent_line(self):
        home = self._home(self.js)
        # categoryCards() renders the "Digital, with intention." strip;
        # brandMark() renders the mark and the line beneath it.
        self.assertLess(home.index('${categoryCards()}'), home.index('${brandMark()}'),
                        'the landing strip must come first')

    def test_the_mark_sits_under_the_landing_not_in_the_hero(self):
        home = self._home(self.js)
        hero = home[home.index('<section class="hero'):home.index('</section>')]
        self.assertNotIn('hero-logo', hero,
                         'the mark was moved out of the hero into its own section')
        start = self.js.index('function brandMark()')
        section = self.js[start:self.js.index('function home(){', start)]
        self.assertIn('hero-logo', section)
        self.assertIn('Independent thinking. Intentional engineering.', section,
                      'the line belongs under the mark it introduces')

    def test_the_hero_copy_is_centred_when_it_stands_alone(self):
        # The hero no longer has a second column to sit beside, so it must not
        # keep the two-column grid: the copy would occupy half the page.
        self.assertIn('hero-solo', self._home(self.js))
        self.assertIn('.hero-solo', self.css)

    def test_a_test_for_this_class_is_not_reading_a_stale_build(self):
        # The class reads the generated root build too, so a stylesheet or
        # bundle that was not regenerated fails here rather than passing on the
        # source alone.
        home = self._home(self.built)
        self.assertIn('categoryCards()', home)
