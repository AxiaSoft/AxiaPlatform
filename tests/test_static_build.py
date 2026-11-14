"""Guards for the generated GitHub Pages build.

The static build has no server, so a single malformed tag in the shell can
disable it silently: an unclosed <script> swallows every following tag as raw
text, which is exactly how the static adapter once disappeared from a build
that still reported success. These tests fail loudly instead.
"""
import json
import shutil
import subprocess
import os
import re
import tempfile
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
    """Two cover shapes, both legal, and neither may double the base.

    A cover uploaded through the console is stored root-absolute ('/brand/x.png')
    and the build adds the Pages sub-path. A cover that comes from the demo
    catalog is stored bare ('brand/x.png') and the storefront adds the base
    through assetUrl(). What must never happen is the prefix stacking up, which
    once turned every cover into /AxiaPlatform/AxiaPlatform/... and 404ed it.
    """

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

    def test_published_catalog_covers_never_carry_the_base_twice(self):
        import json
        data = json.loads((ROOT / 'data' / 'products.json').read_text(encoding='utf-8'))
        for product in data:
            cover = product.get('cover') or ''
            if not cover:
                continue
            self.assertLessEqual(cover.count('/AxiaPlatform/'), 1,
                                 f'{product["slug"]} cover has a doubled base prefix: {cover}')
            # Either shape resolves: assetUrl() prefixes a bare path, and an
            # already-prefixed one is returned unchanged (that is the browser
            # test in AssetPathTests).
            self.assertTrue(
                cover.startswith('brand/') or cover.startswith('/AxiaPlatform/'),
                f'{product["slug"]} cover is neither bare nor base-prefixed: {cover}')

    def test_every_shipped_cover_file_exists(self):
        # A cover that 404s still leaves a box on the card, so only a build-up
        # check catches it. An empty cover is fine — the storefront draws the
        # brand's monogram instead — which is what the demo now ships, since the
        # brand artwork it used to point at is no longer published.
        import json
        data = json.loads((ROOT / 'data' / 'products.json').read_text(encoding='utf-8'))
        for product in data:
            cover = (product.get('cover') or '').lstrip('/')
            if cover.startswith('AxiaPlatform/'):
                cover = cover[len('AxiaPlatform/'):]
            if not cover:
                continue
            self.assertTrue((ROOT / 'public' / cover).is_file(),
                            f'{product["slug"]} points at a missing cover: {cover}')

    def test_a_cover_that_is_empty_still_draws_something(self):
        # The rule the storefront has to honour: image, or monogram, never a
        # blank plate.
        app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('function brandGlyph(', app)
        self.assertIn('cover-glyph', app)


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


class AdminThemeAndLanguageTests(unittest.TestCase):
    """The console's light theme and its two languages.

    Two defects, both invisible to the server tests and both reported from a
    browser:

      * in light mode every panel wore a dark fill. The light block redefined
        the theme variables, but .panel, .stat-card, .login-card, .hero-strip
        and .trend each hardcoded a dark colour instead of reading one, so a
        grey slab landed on a white page.
      * the language direction was one-way. AXIA_T translated to Persian
        regardless of the current language, so an English console printed
        'ذخیره' where it meant 'Save', and strings with no Persian entry stayed
        English in a Persian console.

    These assert the wiring rather than the appearance, because the appearance
    depends on which theme a visitor picked.
    """

    @classmethod
    def setUpClass(cls):
        cls.css = (ROOT / 'public' / 'admin' / 'admin.css').read_text(encoding='utf-8')
        cls.i18n = (ROOT / 'public' / 'i18n.js').read_text(encoding='utf-8')
        cls.admin = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')

    def test_no_panel_paints_a_hardcoded_dark_surface(self):
        import re
        # Any background in the admin sheet whose colour is dark and literal is
        # a light-theme defect waiting to happen. The two overlays (modal and
        # side scrim) are dark on purpose in both themes.
        allowed = {'.modal-backdrop', '.side-scrim'}
        offenders = []
        for m in re.finditer(r'([^{}\n]+)\{([^{}]*)\}', self.css):
            selector, body = m.group(1).strip(), m.group(2)
            if selector in allowed or '[data-theme' in selector:
                continue
            for value in re.findall(r'background(?:-color)?\s*:\s*([^;}]*)', body):
                for rgb in re.findall(r'rgba?\(\s*(\d{1,2})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})', value):
                    if sum(int(v) for v in rgb) < 120:
                        offenders.append((selector[:40], value.strip()[:50]))
        self.assertEqual(offenders, [],
                         'these surfaces would stay dark under the light theme')

    def test_the_light_block_redefines_the_surface_variables(self):
        import re
        light = re.search(r':root\[data-theme="light"\]\{([^}]*)\}', self.css)
        self.assertIsNotNone(light)
        for var in ('--panel-deep', '--trend-bg', '--sidebar-bg', '--hero-tint'):
            self.assertIn(var + ':', light.group(1),
                          f'{var} must be redefined for light mode or its surface keeps the dark fill')

    def test_the_translator_respects_the_current_language(self):
        self.assertIn("document.documentElement.lang!=='fa'", self.i18n,
                      'AXIA_T must return the English source when the page is English')

    def test_every_string_the_console_translates_has_a_persian_entry(self):
        import re

        def keys_near(src, marker):
            i = src.index(marker)
            j = src.index('{', i)
            depth = 0
            for k in range(j, len(src)):
                if src[k] == '{':
                    depth += 1
                elif src[k] == '}':
                    depth -= 1
                    if depth == 0:
                        return set(re.findall(r"[‘'\"]([^‘'\"\\]{2,90})[’'\"]\s*:", src[j:k + 1]))
            return set()

        known = keys_near(self.i18n, 'const fa={') | keys_near(self.i18n, 'Object.assign(fa,{')
        requested = set(re.findall(r"T\('((?:[^'\\]|\\.)*)'\)", self.admin))
        # keys_near() only reads keys of 2-90 characters, because that is the
        # range the lookup table supports. A longer string in the console can
        # therefore never be translated *and* was invisible to this audit: it
        # escaped both the dictionary and the check. Fail on those directly.
        too_long = sorted(k for k in requested if len(k) > 90)
        self.assertEqual(too_long, [],
                         'translatable keys must be 2-90 characters; split these')
        missing = sorted(requested - known)
        self.assertEqual(missing, [],
                         'these stay English in a Persian console')

    def test_no_console_message_skips_the_dictionary(self):
        # T() only helps if it is called. Two messages were handed straight to
        # the login view as English literals, so a Persian console showed a red
        # English box under a Persian heading. The audit above could not see
        # them: it reads the strings that did go through T().
        admin = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')
        for match in re.finditer(r'loginView\(([^)]*)\)', admin):
            argument = match.group(1).strip()
            if not argument or re.search(r'\bT\(', argument):
                continue
            if re.search(r"'[^']{8,}'", argument):
                self.fail(f'loginView() shows untranslated English: {argument[:80]}')

    def test_the_console_never_prints_a_plural_placeholder(self):
        # '(s)' is a note to the developer, not a word. It used to reach the
        # screen: 'project request(s) need a first review.'
        import re
        for m in re.finditer(r"T\('([^']*)'\)", self.admin):
            self.assertNotIn('(s)', m.group(1),
                             f'{m.group(1)!r} would print a plural placeholder')

    def test_an_empty_catalog_can_still_be_asked_for(self):
        # The flag exists so an intentionally empty build stays one command away.
        missing_db = ROOT / 'tests' / 'does-not-exist.sqlite3'
        self.assertEqual(
            build_static.read_catalog(missing_db, '/AxiaPlatform/', demo_catalog=False), [])

    def test_a_build_without_a_database_ships_the_four_builds(self):
        missing_db = ROOT / 'tests' / 'does-not-exist.sqlite3'
        rows = build_static.read_catalog(missing_db, '/AxiaPlatform/')
        self.assertEqual([r['slug'] for r in rows], ['arya', 'ersha', 'mino', 'homa'])
        # A demo row ships without a cover: the brand artwork it used to point
        # at is no longer published, and the storefront draws a monogram.
        self.assertEqual(rows[0]['cover'], '')
        # And the rows carry what a card renders.
        self.assertEqual(len(rows[0]['features']), 4)
        self.assertTrue(rows[0]['published'])



class CategoryTests(unittest.TestCase):
    """Categories are the operator's data, not the site's source code.

    The catalog used to draw its tabs from a literal ['Websites','Applications']
    in public/app.js and the console repeated that list in two more places, so
    renaming one meant editing all three and redeploying. They live in the
    settings document now, which is why an empty list is a valid answer and not
    a broken one.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / 'server'))
        import site_settings
        self.ss = site_settings
        self.admin = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')
        self.app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.demo = (ROOT / 'public' / 'demo-backend.js').read_text(encoding='utf-8')

    def test_a_site_with_no_categories_publishes_none(self):
        self.assertEqual(self.ss.merge({})['categories'], [],
                         'a fresh install must not ship categories of its own')

    def test_a_category_is_an_id_plus_two_labels(self):
        ok, cats = self.ss.clean_category_list(
            [{'id': 'websites', 'name': 'Websites', 'nameFa': 'وب‌سایت‌ها'}])
        self.assertTrue(ok)
        self.assertEqual(cats, [{'id': 'websites', 'name': 'Websites',
                                 'nameFa': 'وب‌سایت‌ها'}])

    def test_category_ids_are_checked(self):
        for bad in ('Web Sites', 'web sites', '', 'A', 'x' * 41, 'web_sites'):
            ok, _ = self.ss.clean_category_list([{'id': bad, 'name': 'X', 'nameFa': ''}])
            self.assertFalse(ok, f'{bad!r} should be refused')

    def test_category_names_are_required_and_unique(self):
        self.assertFalse(self.ss.clean_category_list(
            [{'id': 'web', 'name': '', 'nameFa': ''}])[0])
        self.assertFalse(self.ss.clean_category_list(
            [{'id': 'web', 'name': 'A', 'nameFa': ''},
             {'id': 'web', 'name': 'B', 'nameFa': ''}])[0])

    def test_an_empty_category_list_is_accepted(self):
        # Hiding the tab row is a legitimate choice, not an invalid document.
        self.assertEqual(self.ss.clean_category_list([]), (True, []))

    def test_the_storefront_draws_its_tabs_from_settings(self):
        self.assertIn('function siteCategories()', self.app)
        self.assertIn('site.categories', self.app)
        # The old literals are gone: no tab is hardcoded any more.
        self.assertNotIn("['All','Websites','Applications']", self.app)
        self.assertNotIn("category=Websites", self.app)

    def test_the_console_offers_the_operators_own_categories(self):
        self.assertIn('function siteCategories()', self.admin)
        self.assertIn("data-cat-name", self.admin)
        self.assertIn('function categoryLabel', self.admin)
        # The product form used to hardcode the three display names.
        self.assertNotIn("['Websites','Applications','Aurion'].map", self.admin)

    def test_the_demo_ships_categories_while_the_site_ships_none(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        from demo_catalog import DEMO_CATEGORIES
        self.assertTrue(DEMO_CATEGORIES)
        self.assertEqual(self.ss.clean_category_list(DEMO_CATEGORIES)[0], True)
        # Every demo product sits in one of the demo's categories.
        from demo_catalog import DEMO_CATALOG
        ids = {c['id'] for c in DEMO_CATEGORIES}
        for row in DEMO_CATALOG:
            self.assertIn(row['category'], ids, f'{row["slug"]} has no category')

    def test_the_demo_backend_validates_categories_like_the_server(self):
        self.assertIn('categories: \'categories\'', self.demo)
        self.assertIn('function validateCategories', self.demo)
        self.assertIn('CATEGORY_ID_RE', self.demo)



class EmbeddedPreviewTests(unittest.TestCase):
    """A product preview opens inside the site, full screen.

    The button used to send the visitor to GitHub in a new tab, and a product
    without a link fell back to a small card at the bottom of its detail page.
    Both are gone: one layer covers the page, frames the target, and closes back
    onto the catalog.
    """

    def setUp(self):
        self.app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')

    def test_a_card_preview_is_a_button_not_a_new_tab(self):
        self.assertIn('data-preview=', self.app)
        # The old markup opened the repository in a separate tab.
        self.assertNotIn('target="_blank" rel="noopener noreferrer">Preview ↗', self.app)

    def test_the_layer_covers_the_viewport(self):
        layer = self.css[self.css.index('.preview-layer {'):]
        block = layer[:layer.index('}')]
        self.assertIn('position: fixed', block)
        self.assertIn('inset: 0', block)
        self.assertIn('z-index: 60', block,
                      'the preview must sit above the modals at 50')

    def test_the_frame_is_sandboxed(self):
        self.assertIn('sandbox="allow-scripts allow-same-origin allow-popups', self.app)
        # A frame must never be given the power to navigate the top window.
        self.assertNotIn('allow-top-navigation', self.app)

    def test_escape_closes_the_layer(self):
        self.assertIn("event.key === 'Escape'", self.app)
        self.assertIn('function closePreview', self.app)

    def test_a_product_without_a_link_frames_a_generated_page(self):
        self.assertIn('data/preview/', self.app)
        path = ROOT / 'data' / 'preview'
        if path.is_dir():
            for page in path.glob('*.html'):
                text = page.read_text(encoding='utf-8')
                # Self-contained: no script, no external request.
                self.assertNotIn('<script', text, f'{page.name} must not run script')
                self.assertIn('concept preview', text)


class CompressionTests(unittest.TestCase):
    """Static files are served gzipped. The stdlib handler copied them raw."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / 'server'))

    def test_text_is_compressed_and_binary_is_not(self):
        import app as server_app
        import tempfile
        css = Path(tempfile.mkdtemp()) / 'x.css'
        css.write_text('body{' + 'color:red;' * 400 + '}', encoding='utf-8')
        body, encoding = server_app.compressed_static(css, 'text/css', 'gzip')
        self.assertEqual(encoding, 'gzip')
        self.assertLess(len(body), css.stat().st_size)

        png = Path(tempfile.mkdtemp()) / 'x.png'
        png.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 2000)
        raw, encoding = server_app.compressed_static(png, 'image/png', 'gzip')
        self.assertIsNone(encoding, 'an already-compressed image must be sent as-is')
        self.assertEqual(raw, png.read_bytes())

    def test_a_client_that_did_not_ask_gets_plain_bytes(self):
        import app as server_app
        import tempfile
        js = Path(tempfile.mkdtemp()) / 'x.js'
        js.write_text('var a = 1;' * 400, encoding='utf-8')
        raw, encoding = server_app.compressed_static(js, 'application/javascript', '')
        self.assertIsNone(encoding)
        self.assertEqual(raw, js.read_bytes())

    def test_the_cache_key_follows_the_file(self):
        # A rebuild replaces the file; serving yesterday's compressed body would
        # be a silent stale-CSS bug.
        import app as server_app
        import tempfile
        target = Path(tempfile.mkdtemp()) / 'x.css'
        target.write_text('a{' + 'x:1;' * 500 + '}', encoding='utf-8')
        first, _ = server_app.compressed_static(target, 'text/css', 'gzip')
        target.write_text('b{' + 'y:2;' * 500 + '}', encoding='utf-8')
        os.utime(target, (0, 0))
        second, _ = server_app.compressed_static(target, 'text/css', 'gzip')
        self.assertNotEqual(first, second)


class MarqueeTests(unittest.TestCase):
    """The promise strip under the hero buttons travels instead of sitting still."""

    def setUp(self):
        self.app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')

    def test_the_list_is_written_twice(self):
        self.assertIn('function trustMarquee', self.app)
        self.assertIn('${items}${items}', self.app,
                      'the loop needs two copies to hide its reset')

    def test_the_scroll_moves_exactly_half_the_track(self):
        start = self.css.index('@keyframes trustScroll')
        block = self.css[start:self.css.index('}}', start) + 2]
        # Half, not a full width: the track holds two copies of the list, so
        # stopping at -50% hands the second copy exactly where the first began
        # and the jump back to 0 is invisible.
        self.assertIn('translateX(-50%)', block)

    def test_the_direction_follows_the_document(self):
        # translateX is physical, so the rtl belt needs its own keyframe: an
        # English visitor sees it slide left, a Persian one sees it slide right.
        self.assertIn('.trust-track{display:flex', self.css)
        start = self.css.index('@keyframes trustScrollRtl')
        block = self.css[start:self.css.index('}}', start) + 2]
        self.assertIn('translateX(50%)', block)
        self.assertNotIn('translateX(-50%)', block)
        self.assertRegex(self.css, r'html\[dir="rtl"\]\s*\.trust-track\s*\{\s*animation-name:\s*trustScrollRtl')

    def test_it_stops_for_reduced_motion(self):
        tail = self.css[self.css.rindex('prefers-reduced-motion'):]
        self.assertIn('.trust-track { animation: none; }', tail)



class AdminLayoutTests(unittest.TestCase):
    """The console's navigation and catalog screen across screen sizes.

    Three separate complaints from the operator, all about the same sidebar:
    it scrolled away with the page on a short laptop, the hamburger survived on
    a desktop where there was already a full menu, and the products screen was
    one wide table on every device.
    """

    def setUp(self):
        self.css = (ROOT / 'public' / 'admin' / 'admin.css').read_text(encoding='utf-8')
        self.js = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')

    def test_the_sidebar_scrolls_inside_a_short_window(self):
        start = self.css.index('.sidebar{')
        block = self.css[start:self.css.index('}', start)]
        self.assertIn('overflow-y:auto', block)
        # Without this a flick at the end of the list scrolls the page behind it.
        self.assertIn('overscroll-behavior:contain', block)

    # The stylesheet is written partly by hand and partly minified, so a rule
    # may appear as `@media (max-width: 760px)` or `@media(max-width:760px)`.
    # These helpers read either.
    def _blocks(self, kind, width):
        pattern = r'@media\s*\(' + kind + r':\s*' + str(width) + r'px\)\s*\{'
        for match in re.finditer(pattern, self.css):
            depth, i = 0, match.end() - 1
            while i < len(self.css):
                if self.css[i] == '{':
                    depth += 1
                elif self.css[i] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            yield self.css[match.end():i]

    def test_there_is_no_hamburger_on_a_desktop(self):
        # The drawer and its toggle are a phone affordance only. !important
        # because the drawer rule sets display on the same element.
        self.assertRegex(self.css, r'\.mobile-toggle\s*\{\s*display:\s*none\s*!important')
        self.assertTrue(any('.mobile-toggle' in b for b in self._blocks('max-width', 760)))
        # And nothing above that breakpoint may ever reveal it again.
        for width in (761, 900, 901, 1024, 1200):
            for block in self._blocks('min-width', width):
                self.assertNotRegex(block, r'\.mobile-toggle\s*\{[^}]*display:\s*grid')

    def test_the_drawer_keyword_only_applies_below_the_breakpoint(self):
        blocks = list(self._blocks('max-width', 760))
        self.assertTrue(blocks, 'no phone breakpoint block found')
        self.assertTrue(any('.sidebar.open' in b for b in blocks))

    def test_the_catalog_is_a_table_only_where_a_table_fits(self):
        # Only one layout may exist at a time: rendering both put every product
        # in the DOM twice.
        self.assertIn('function compact()', self.js)
        self.assertIn("matchMedia('(max-width: 900px)')", self.js)
        self.assertIn("${compact()?productCards(", self.js)
        self.assertNotIn("${productsTable(data,allShownSelected)}${productCards(", self.js)

    def test_a_resize_swaps_the_layout_without_a_reload(self):
        self.assertIn("query.addEventListener('change'", self.js)

    def test_the_card_list_carries_the_same_controls_as_the_table(self):
        # Whatever is reachable in the table has to stay reachable in the cards,
        # or an action disappears on a phone. The two layouts share the action
        # block for exactly this reason, so the check is that they both use it.
        cards = self.js[self.js.index('function productCards('):]
        cards = cards[:cards.index('\nfunction ', 10)]
        table = self.js[self.js.index('function productsTable('):]
        table = table[:table.index('\nfunction ', 10)]
        for layout, name in ((cards, 'cards'), (table, 'table')):
            self.assertIn('${productActions(p)}', layout,
                          f'the {name} layout must use the shared action block')
        actions = self.js[self.js.index('function productActions('):]
        actions = actions[:actions.index('\nfunction ', 10)]
        for hook in ('feature-product', 'edit-product', 'toggle-product'):
            self.assertIn(hook, actions, f'the shared actions lost {hook}')



class CacheBusterTests(unittest.TestCase):
    """Every asset that can change carries a version marker.

    A missing or stale marker is invisible in development — the file is served
    fresh from disk — and shows up days later as a visitor running old JS against
    new HTML. This checks the markers exist and, more usefully, that they are not
    shared by two different files, which is what happened every round when one
    page kept ?v=static-1 while its neighbour moved on.
    """

    def setUp(self):
        self.index = (ROOT / 'public' / 'index.html').read_text(encoding='utf-8')
        self.console = (ROOT / 'public' / 'admin' / 'index.html').read_text(encoding='utf-8')
        self.build = (ROOT / 'tools' / 'build_static.py').read_text(encoding='utf-8')

    def _versions(self, html):
        found = {}
        for asset, version in re.findall(r'([\w/-]+\.(?:css|js))\?v=([\w.-]+)', html):
            found.setdefault(asset, set()).add(version)
        return found

    def test_every_local_asset_is_versioned(self):
        for name, html in (('storefront', self.index), ('console', self.console)):
            for src in re.findall(r'(?:href|src)="(/[^"]+\.(?:css|js))"', html):
                self.fail(f'{name} loads {src} with no ?v= marker')

    def test_no_asset_is_listed_at_two_versions(self):
        for name, html in (('storefront', self.index), ('console', self.console)):
            for asset, versions in self._versions(html).items():
                self.assertEqual(len(versions), 1,
                                 f'{name} loads {asset} as {sorted(versions)}')

    def test_the_build_injects_versioned_tags_too(self):
        # The snapshots and the adapter are written by the build, not present in
        # the source page, so the source-page check cannot see them.
        for asset in ('static-config.js', 'static-adapter.js',
                      'data/products.js', 'data/settings.js', 'demo-backend.js'):
            self.assertIn(f'{asset}?v=', self.build, f'{asset} is injected unversioned')

    def test_the_markers_differ_between_files(self):
        # Two files sharing one marker means a bump of either invalidates both,
        # and the next author is tempted to stop bumping rather than churn.
        versions = {}
        for html in (self.index, self.console):
            for asset, vs in self._versions(html).items():
                versions.setdefault(asset, set()).update(vs)
        bumps = [re.search(r'\?v=([\w.-]+)', line) for line in self.build.splitlines()]
        bumps = [b.group(1) for b in bumps if b and 'static' in b.group(1)]
        self.assertTrue(len(set(bumps)) > 1,
                        'the injected snapshots all share one marker')



class FontTests(unittest.TestCase):
    """The Persian webfont is a subset, and the full one is never published.

    Vazirmatn ships every Arabic-script glyph upstream supports; the site can
    only draw the characters in its own strings. The subset is 61% of the size
    and renders identically, but it only stays small if the build stops there
    and the full file never reaches the deployed tree.
    """

    def test_the_shipped_font_is_the_subset(self):
        subset = ROOT / 'public' / 'fonts' / 'Vazirmatn-Variable.woff2'
        full = ROOT / 'tools' / 'assets' / 'Vazirmatn-Variable.full.woff2'
        self.assertTrue(subset.is_file())
        self.assertTrue(full.is_file(), 'the subset cannot be rebuilt without it')
        self.assertLess(subset.stat().st_size, full.stat().st_size * 0.75,
                        'the published font has grown back towards the original')

    def test_the_full_font_is_not_in_the_public_tree(self):
        # If it were, the build would copy it and every visitor would be one
        # mistyped href away from downloading it for nothing.
        self.assertFalse((ROOT / 'public' / 'fonts' /
                          'Vazirmatn-Variable.full.woff2').exists())

    def test_the_subset_keeps_the_persian_alphabet(self):
        # fontTools is a build-time dependency of tools/subset_font.py, not of
        # the site, so the suite still runs where it is not installed.
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            self.skipTest('fontTools is not installed')
        font = TTFont(str(ROOT / 'public' / 'fonts' / 'Vazirmatn-Variable.woff2'))
        cmap = font.getBestCmap()
        # The letters Persian prose actually uses, plus its digits and the
        # zero-width non-joiner that appears inside words like می‌سازیم.
        for ch in 'ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی':
            self.assertIn(ord(ch), cmap, f'{ch} is missing from the subset')
        for ch in '۰۱۲۳۴۵۶۷۸۹':
            self.assertIn(ord(ch), cmap, f'{ch} is missing from the subset')
        self.assertIn(0x200C, cmap, 'the zero-width non-joiner must survive')



class BlogTranslationTests(unittest.TestCase):
    """A Persian post has an English mirror that is actually in English.

    The pipeline existed but nothing produced its input: `data/translations.json`
    was never written by any tool and the build only looked for it in the output
    tree, so a committed translation was ignored and /en/blog/ fell back to the
    untranslated notice. Three separate breaks, each of which looks like "the
    blog is not translated".
    """

    def setUp(self):
        self.build = (ROOT / 'tools' / 'build_static.py').read_text(encoding='utf-8')
        self.tool = (ROOT / 'tools' / 'translate_articles.py').read_text(encoding='utf-8')

    def test_a_tool_exists_to_produce_the_translations(self):
        self.assertIn('translations.json', self.tool)
        # It must be runnable without arguments and must not write without a
        # provider — a guessed translation is worse than an honest notice.
        self.assertIn('translation_available()', self.tool)
        self.assertIn('AXIA_AGENT_KEY', self.tool)

    def test_the_hash_matches_the_console_so_both_agree_on_staleness(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        import translate_articles
        import hashlib
        article = {'title': 'a', 'summary': 'b', 'body': 'c'}
        source = '\n\x00\n'.join(['a', 'b', 'c'])
        expected = hashlib.sha256(source.encode('utf-8')).hexdigest()[:32]
        self.assertEqual(translate_articles.digest(article), expected)

    def test_the_build_reads_the_repository_copy_first(self):
        # The bug: only `out/data/translations.json` was consulted, so a clean
        # build never saw the committed file.
        self.assertIn("ROOT / 'data' / 'translations.json'", self.build)
        source_first = self.build.index("ROOT / 'data' / 'translations.json'")
        out_copy = self.build.index("out / 'data' / 'translations.json'")
        self.assertLess(source_first, out_copy,
                        'the output copy is being read before the source')

    def test_the_build_ships_the_translations(self):
        # A client-side reader of data/*.json should see the same copy.
        self.assertIn("(data_dir / 'translations.json')", self.build)

    def test_the_build_names_the_command_when_a_post_is_owed(self):
        self.assertIn('tools/translate_articles.py', self.build)

    def test_the_published_article_has_english_copy(self):
        articles = json.loads((ROOT / 'data' / 'articles.json').read_text(encoding='utf-8'))
        stored = json.loads((ROOT / 'data' / 'translations.json').read_text(encoding='utf-8'))
        sys.path.insert(0, str(ROOT / 'tools'))
        import translate_articles
        for article in articles:
            if str(article.get('language') or 'fa') != 'fa':
                continue
            entry = stored.get(article['slug'])
            self.assertIsNotNone(entry, f'{article["slug"]} has no English copy')
            self.assertEqual(entry['source_hash'], translate_articles.digest(article),
                             f'{article["slug"]} translation is stale')
            # The body has to be real prose, not the source echoed back.
            self.assertGreater(len(entry['body']), 100)
            self.assertNotIn('چطور', entry['title'])


class BrandArtworkTests(unittest.TestCase):
    """Brands carry no shipped artwork; an operator uploads their own.

    The four brands shipped with the studio's own logo files. Those are gone: the
    site does not publish drawings it does not own, and the console now takes an
    upload for each of the two image slots. What has to keep working is the case
    where a brand has no image at all.
    """

    def setUp(self):
        self.app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.brands = (ROOT / 'public' / 'brands.js').read_text(encoding='utf-8')
        self.admin = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')

    def test_a_brand_without_an_image_is_still_usable(self):
        # usable() required a mark, which silently dropped every brand on a
        # fresh install — the picker just looked empty.
        start = self.brands.index('function usable(brand)')
        block = self.brands[start:self.brands.index('}', start)]
        self.assertNotIn("String(brand.mark || '').trim()", block)

    def test_the_storefront_draws_a_monogram(self):
        self.assertIn('function brandGlyph(', self.app)
        self.assertIn('brand-glyph', self.app)
        # The initial follows the language being read.
        self.assertIn('brandName(brand)', self.app)

    def test_the_console_uploads_a_brand_image(self):
        self.assertIn('data-brand-asset-file', self.admin)
        self.assertIn('data-brand-asset-path', self.admin)
        self.assertIn('brandSwatch', self.admin)

    def test_the_upload_keeps_the_bytes_for_a_logo(self):
        # A logo is line art: re-encoding puts a fringe on a transparent edge.
        self.assertIn("headers['X-Upload-Raw'] = '1'", self.admin)
        server = (ROOT / 'server' / 'app.py').read_text(encoding='utf-8')
        self.assertIn('X-Upload-Raw', server)
        self.assertIn('raw=raw', server)

    def test_an_svg_is_sandboxed_when_served(self):
        server = (ROOT / 'server' / 'app.py').read_text(encoding='utf-8')
        self.assertIn("if suffix == '.svg':", server)
        self.assertIn("default-src 'none'", server)


class MarqueeBehaviourTests(unittest.TestCase):
    def test_the_strip_never_pauses(self):
        css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')
        self.assertNotIn('animation-play-state:paused', css)
        self.assertIn('.trust-strip{pointer-events:none}', css)


class BrandCatalogTests(unittest.TestCase):
    """The site brands are data, not source.

    They used to be four objects hardcoded in public/brands.js, so adding a fifth
    meant editing code and redeploying. The administrator asked for them to be
    managed from the console instead. These tests hold that line: the storefront
    must read them from the settings document, and the file that used to carry
    them must not carry them any more.
    """

    def setUp(self):
        self.brands_js = (ROOT / 'public' / 'brands.js').read_text(encoding='utf-8')
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.admin_js = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')

    def test_no_brand_names_are_hardcoded_in_the_storefront(self):
        # Comments are allowed to mention the names — that is how a reader
        # learns what the file is for. Only code counts.
        import re

        def code(src):
            src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
            return re.sub(r'(?m)^\s*//.*$', '', src)

        for name in ('Arya', 'Ersha', 'Mino', 'Homa', 'آریا', 'ارشا', 'مینو', 'هما'):
            self.assertNotIn(name, code(self.brands_js),
                             f'{name!r} is still baked into brands.js')
            self.assertNotIn(name, code(self.app_js),
                             f'{name!r} is still baked into app.js')

    def test_the_brand_list_comes_from_the_settings_snapshot(self):
        self.assertIn('AXIA_STATIC.settings.brands', self.brands_js)
        self.assertIn('AXIA_BRANDS_APPLY', self.brands_js)

    def test_the_shipped_snapshot_carries_brands(self):
        import json
        data = json.loads((ROOT / 'data' / 'settings.json').read_text(encoding='utf-8'))
        self.assertIsInstance(data.get('brands'), list)
        self.assertTrue(data['brands'], 'the sites ships with no brands at all')
        for brand in data['brands']:
            # The image is the operator's to supply. Everything that makes the
            # brand identifiable has to be there; the artwork does not.
            for field in ('id', 'name', 'nameFa', 'accent'):
                self.assertTrue(brand.get(field), f'{brand.get("id")} has no {field}')
            self.assertIn(brand.get('mark', ''), ('', None),
                          f'{brand.get("id")} ships artwork the site does not own')

    def test_the_console_edits_brands(self):
        self.assertIn("['brands'", self.admin_js)
        self.assertIn('brandsTabHTML', self.admin_js)
        self.assertIn('saveBrands', self.admin_js)

    def test_a_product_without_a_cover_falls_back_to_a_logo(self):
        # The administrator's rule: no cover must never mean an empty plate.
        self.assertIn('is-emblem', self.app_js)
        self.assertIn('axiasoft-original.png', self.app_js)
        styles = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')
        self.assertIn('.product-cover.is-emblem', styles)
        self.assertIn('.product-cover.is-default', styles)

    def test_brand_cards_tilt_and_glow_and_stack_on_a_phone(self):
        self.assertIn('brand-pick tilt-hover mouse-light', self.app_js)
        styles = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')
        # The flat hover lift must not survive next to the 3D tilt: same
        # specificity, declared later, it silently cancels the rotation.
        hover = styles[styles.index('.brand-pick:hover'):]
        hover = hover[:hover.index('}')]
        self.assertNotIn('transform', hover,
                         'the hover transform cancels the 3D tilt')
        # A phone gets one row of four tiles, not one column of four cards: the
        # cards turn vertical so the logos can sit side by side and be compared
        # at a glance.
        phone = styles[styles.index('@media (max-width: 640px) {'):]
        phone = phone[:phone.index('\n}')]
        self.assertIn('.brand-picker-row { grid-template-columns: repeat(4', phone,
                      'the phone layout is not a single row of four')
        self.assertIn('flex-direction: column', phone,
                      'the tiles must stack logo-over-name at this width')
        self.assertIn('.brand-pick-copy small { display: none; }', phone)
        self.assertNotIn('grid-template-columns: 1fr;', styles.split('@media (max-width: 640px) {')[1][:400],
                         'a leftover single-column rule would cancel the row')

    def test_every_brand_reference_the_console_prints_is_translated(self):
        i18n = (ROOT / 'public' / 'i18n.js').read_text(encoding='utf-8')
        for word in ('Site brands', 'brand', 'brands'):
            self.assertIn(f'"{word}":', i18n, f'{word!r} has no Persian entry')


class BrandValidationTests(unittest.TestCase):
    """A brand drives the header lockup and every accent colour on the page, so
    a malformed one is worse than a missing one. Both the Python server and the
    browser demo must refuse the same payloads."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / 'server'))
        import site_settings
        self.settings = site_settings

    def _brand(self, **over):
        brand = dict(self.settings.DEFAULTS['brands'][0])
        brand.update(over)
        return brand

    def test_the_shipped_defaults_are_valid(self):
        ok, brands = self.settings.clean_value('brands', self.settings.DEFAULTS['brands'])
        self.assertTrue(ok)
        self.assertEqual(len(brands), 4)

    def test_the_shipped_brands_carry_no_artwork(self):
        # The four brands shipped with the studio's own logo files. Those are
        # gone: the site does not publish somebody else's drawings, and an
        # operator uploads their own marks in the console. The defaults must
        # therefore validate with empty paths.
        for brand in self.settings.DEFAULTS['brands']:
            self.assertEqual(brand['mark'], '', f"{brand['id']} still ships a mark")
            self.assertEqual(brand['logo'], '', f"{brand['id']} still ships a logo")

    def test_no_brand_artwork_is_left_in_the_tree(self):
        for name in ('arya', 'ersha', 'mino', 'homa'):
            for kind in ('mark', 'logo'):
                path = ROOT / 'public' / 'brand' / f'{name}-{kind}.png'
                self.assertFalse(path.exists(), f'{path.name} is still published')

    def test_a_brand_may_have_no_image_at_all(self):
        ok, brand = self.settings.clean_brand(
            {'id': 'arya', 'name': 'Arya', 'nameFa': 'آریا', 'tagline': 'x',
             'taglineFa': 'x', 'accent': '#1f5fa8', 'accentSoft': '#3f8ad8',
             'mark': '', 'logo': ''}, set())
        self.assertIsNone(brand and None if not ok else None,
                          'an image-less brand must validate')

    def test_a_brand_path_still_has_to_be_servable(self):
        for bad in ('javascript:alert(1)', '../etc/passwd', 'brand/x.png" onerror='):
            ok, _ = self.settings.clean_brand(
                {'id': 'arya', 'name': 'Arya', 'nameFa': '', 'tagline': 'x',
                 'taglineFa': '', 'accent': '#1f5fa8', 'accentSoft': '#3f8ad8',
                 'mark': bad, 'logo': ''}, set())
            self.assertFalse(ok, f'{bad!r} should be refused')

    def test_an_empty_list_is_allowed(self):
        # The administrator asked to be able to remove them, so none is a real
        # choice and must not be an error.
        self.assertEqual(self.settings.clean_value('brands', []), (True, []))

    def test_duplicate_ids_are_refused(self):
        one = self._brand()
        ok, _ = self.settings.clean_value('brands', [one, dict(one)])
        self.assertFalse(ok)

    def test_a_colour_that_is_not_hex_is_refused(self):
        ok, _ = self.settings.clean_value('brands', [self._brand(accent='blue')])
        self.assertFalse(ok)

    def test_a_script_url_is_refused_as_a_mark(self):
        # These values reach an <img src>, so a javascript: or data: URL is an
        # injection vector, not a path.
        for bad in ('javascript:alert(1)', 'data:image/svg+xml,<svg>', '../../etc/passwd'):
            ok, _ = self.settings.clean_value('brands', [self._brand(mark=bad)])
            self.assertFalse(ok, f'{bad!r} was accepted as a mark')

    def test_relative_and_absolute_asset_paths_are_both_accepted(self):
        for good in ('brand/x-mark.png', '/brand/x-mark.png', 'https://example.test/x.png'):
            ok, _ = self.settings.clean_value('brands', [self._brand(mark=good)])
            self.assertTrue(ok, f'{good!r} was refused')

    def test_more_than_twelve_brands_are_refused(self):
        many = [self._brand(id=f'b{i}') for i in range(13)]
        ok, _ = self.settings.clean_value('brands', many)
        self.assertFalse(ok)

    def test_brands_survive_a_settings_round_trip(self):
        merged = self.settings.merge({'brands': [self._brand(name='Zed', id='zed')]})
        self.assertEqual([b['id'] for b in merged['brands']], ['zed'])


class BrandEditorTranslationsTests(unittest.TestCase):
    """The brand editor must be fully Persian in a Persian console.

    Round 11 fixed the console's English leaks, and this new tab arrived after
    it. The guard is repeated here so a label added to the editor in English
    fails a test rather than shipping to a Persian administrator.
    """

    def setUp(self):
        self.admin_js = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')
        i18n = (ROOT / 'public' / 'i18n.js').read_text(encoding='utf-8')
        self.i18n = i18n

    def _brand_editor_source(self):
        start = self.admin_js.index('function brandRowHTML')
        end = self.admin_js.index('function siteTabHTML')
        return self.admin_js[start:end]

    def test_the_editor_has_no_untranslated_prose(self):
        # Every visible label in the editor goes through T(). The check is a
        # list of words that appeared in the first draft in English.
        src = self._brand_editor_source()
        for leaked in ('Name (English)', 'Accent colour', 'Header mark',
                       'Card logo', 'Add brand', 'Save brands'):
            self.assertNotIn('>' + leaked + '<', src,
                             f'{leaked!r} is printed without T()')
            self.assertNotIn('"' + leaked + '"', src.replace('T("', ''),
                             f'{leaked!r} is printed without T()')

    def test_every_editor_string_is_in_the_dictionary(self):
        import re

        def keys_near(src, marker):
            i = src.index(marker)
            j = src.index('{', i)
            depth = 0
            for k in range(j, len(src)):
                if src[k] == '{':
                    depth += 1
                elif src[k] == '}':
                    depth -= 1
                    if depth == 0:
                        return set(re.findall(r"[‘'\"]([^‘'\"\\]{2,90})[’'\"]\s*:", src[j:k + 1]))
            return set()

        known = keys_near(self.i18n, 'const fa={') | keys_near(self.i18n, 'Object.assign(fa,{')
        requested = set(re.findall(r"T\('((?:[^'\\]|\\.)*)'\)",
                                   self._brand_editor_source()))
        self.assertEqual(sorted(requested - known), [],
                         'these stay English in the Persian console')

    def test_translatable_keys_stay_under_ninety_characters(self):
        # The dictionary scanner in the tests above only sees keys up to 90
        # characters; a longer key is silently invisible to it and would slip
        # through untranslated. Kept as a rule of its own so the limit is stated
        # once rather than implied by a regex.
        import re
        for m in re.finditer(r"T\('((?:[^'\\]|\\.)*)'\)", self.admin_js):
            self.assertLessEqual(len(m.group(1)), 90,
                                 f'{m.group(1)[:60]!r} is too long to be checked')


class AssetPathTests(unittest.TestCase):
    """Asset URLs are built once, not twice.

    The browser check found /AxiaPlatform/AxiaPlatform/brand/arya-logo.png: the
    build had already prefixed the product cover with the deploy base, and
    assetUrl() prefixed it again. A 404 there is invisible in a screenshot —
    the cover box stays, the picture is just gone — which is why it is tested.
    """

    def setUp(self):
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.admin_js = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')

    def test_asset_url_returns_an_already_prefixed_path_unchanged(self):
        # Runs the shipped assetUrl() itself, extracted from app.js, rather than
        # a copy of its logic: a copy would keep passing after the original
        # regressed.
        if not shutil.which('node'):
            self.skipTest('node is not installed')
        script = ASSET_URL_PROBE
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as fh:
            fh.write(script)
            path = fh.name
        try:
            out = subprocess.run(['node', path, str(ROOT / 'public' / 'app.js')],
                                 capture_output=True, text=True, timeout=60)
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(out.returncode, 0, out.stderr[:400])
        already, bare, rooted = json.loads(out.stdout)
        self.assertEqual(already, '/AxiaPlatform/brand/a.png',
                         'the deploy base was applied twice')
        self.assertEqual(bare, '/AxiaPlatform/brand/a.png')
        self.assertEqual(rooted, '/AxiaPlatform/brand/a.png')

    def test_the_console_resolves_assets_without_static_config(self):
        # The console page never loads static-config.js, so AXIA_STATIC.base is
        # undefined there and brand marks fell back to the server root.
        self.assertIn('location.pathname.replace', self.admin_js,
                      'the console must derive the deploy base from its own path')
        self.assertNotIn('window.AXIA_BASE', self.admin_js,
                         'there is no such global; assets 404 at the root')


# Extracts the shipped assetUrl() and reports what it returns for the three
# shapes of asset path the build produces. Kept as a separate constant so the
# backslashes in its regular expressions survive verbatim.
ASSET_URL_PROBE = """
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');  // argv[1] is this script
global.window = { AXIA_STATIC: { base: '/AxiaPlatform/' } };
global.document = { currentScript: null };
global.location = { pathname: '/AxiaPlatform/' };
// Locate the function by plain string search: a regex literal here would have
// to survive Python's own string escaping, and one wrong backslash makes the
// test fail for a reason that has nothing to do with assetUrl.
const NL = String.fromCharCode(10);
const start = src.indexOf(NL + 'function assetUrl(path) {');
const body = start + (NL + 'function assetUrl(path) {').length;
const end = src.indexOf(NL + '}' + NL, body);
if (start < 0 || end < 0) throw new Error('assetUrl not found in app.js');
const assetUrl = new Function(src.slice(start, end + 2) + '; return assetUrl;')();
console.log(JSON.stringify([
  assetUrl('/AxiaPlatform/brand/a.png'),
  assetUrl('brand/a.png'),
  assetUrl('/brand/a.png'),
]));
"""

class CatalogShipsEmptyTests(unittest.TestCase):
    """Two builds, two catalog policies.

    The Python server holds its catalog in SQLite and starts empty: an operator
    creates products in the console. The serverless build on Pages has no
    database, so it is the demo and ships a catalog of its own — otherwise a
    visitor who cannot run the server would find nothing to look at.

    The four website builds live in tools/demo_catalog.py. data/products.json is
    the build output for whatever the operator published, and is not a source
    the demo quietly repopulates itself from.
    """

    def setUp(self):
        self.snapshot = json.loads((ROOT / 'data' / 'products.json').read_text(encoding='utf-8'))
        self.demo = (ROOT / 'public' / 'demo-backend.js').read_text(encoding='utf-8')
        self.adapter = (ROOT / 'public' / 'static-adapter.js').read_text(encoding='utf-8')
        self.build = (ROOT / 'tools' / 'build_static.py').read_text(encoding='utf-8')
        sys.path.insert(0, str(ROOT / 'tools'))
        from demo_catalog import DEMO_CATALOG
        self.catalog = DEMO_CATALOG

    def test_the_server_starts_with_no_products(self):
        # The server never reads data/products.json; its catalog is the database.
        sys.path.insert(0, str(ROOT / 'server'))
        import db as server_db
        self.assertEqual(server_db.SEED_PRODUCTS, [],
                         'the server must not seed products of its own')

    def test_the_demo_build_ships_the_website_builds(self):
        self.assertEqual([row['slug'] for row in self.catalog],
                         ['arya', 'ersha', 'mino', 'homa'])

    def test_the_demo_catalog_is_a_fallback_not_a_precedence(self):
        self.assertIn('if not rows and demo_catalog:', self.build)
        # The implicit "reuse data/products.json" fallback is gone: it let the
        # catalog repopulate itself from an old build, so no one could tell
        # which file was the source of truth.
        self.assertNotIn("published = ROOT / 'data' / 'products.json'", self.build)

    def test_a_datas_own_rows_win_over_the_demo_catalog(self):
        # An operator with a real catalog must never see demo rows mixed in.
        import sqlite3
        tmp = Path(tempfile.mkdtemp()) / 'catalog.sqlite3'
        conn = sqlite3.connect(tmp)
        conn.execute(
            'CREATE TABLE products (id INTEGER PRIMARY KEY, slug TEXT, title TEXT, '
            'category TEXT, summary TEXT, description TEXT, cover TEXT, features TEXT, '
            'technologies TEXT, status TEXT, price_label TEXT, published INTEGER, '
            'created_at TEXT)')
        conn.execute(
            "INSERT INTO products VALUES (1,'only-real','Only Real','Websites','s','d',"
            "'/brand/x.png','[]','[]','available','',1,'')")
        conn.commit(); conn.close()
        rows = build_static.read_catalog(tmp, '/AxiaPlatform/')
        self.assertEqual([r['slug'] for r in rows], ['only-real'])

    def test_the_console_page_loads_the_product_snapshot(self):
        # demo-backend.js seeds the console's catalog from AXIA_STATIC.products.
        # Without this tag the demo console opened on an empty catalog while the
        # public site shipped four products, so the panel disagreed with the site
        # it manages.
        built = ROOT / 'admin' / 'index.html'
        html = built.read_text(encoding='utf-8')
        self.assertIn('demo-backend.js', html)
        self.assertIn('data/products.js', html,
                      'the console cannot seed its catalog without the snapshot')
        # Order matters: the snapshot has to be defined before demo-backend runs.
        self.assertLess(html.index('data/products.js'), html.index('demo-backend.js'))
        self.assertIn('products_tag', self.build,
                      'the build no longer injects the product snapshot')

    def test_the_demo_catalog_rows_are_complete(self):
        for row in self.catalog:
            # `cover` is deliberately absent from this list: a demo product has
            # no artwork, and the storefront draws the brand's monogram. Every
            # other field is what a card renders.
            for field in ('slug', 'title', 'category', 'summary', 'description',
                          'features', 'technologies', 'status', 'price_label'):
                self.assertTrue(row.get(field) not in (None, ''),
                                f'{row.get("slug")} has no {field}')
            cover = row.get('cover') or ''
            if cover:
                self.assertFalse(cover.startswith('/'),
                                 f'{row["slug"]} cover is pre-prefixed')

    def test_the_demo_seeds_are_only_written_on_request(self):
        # The seed list is a constant; nothing may call the loader while the page
        # is merely loading, or the public catalog would fill itself.
        loader = self.demo[self.demo.index('window.AXIA_DEMO_SAMPLES'):]
        body = loader[:loader.index('window.AXIA_DEMO_RESET')]
        self.assertIn('writeProducts', body)
        before = self.demo[:self.demo.index('window.AXIA_DEMO_SAMPLES')]
        self.assertNotIn('AXIA_DEMO_SAMPLES()', before,
                         'the sample catalog is being loaded automatically')

    def test_the_console_reaches_the_storefront_through_the_demo_store(self):
        # The console writes localStorage; the public page has to read it back,
        # otherwise products added in the demo never appear on the site.
        self.assertIn("'axia-demo-products-v1'", self.demo)
        self.assertIn("'axia-demo-products-v1'", self.adapter)
        self.assertIn('demoProducts()', self.adapter)
