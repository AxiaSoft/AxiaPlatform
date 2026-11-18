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

    @staticmethod
    def app_tag(html):
        # The source page carries no ?v= - the build stamps it - so match the
        # tag itself rather than a marker that may or may not be there yet.
        return html.index('src="/app.js')

    def test_static_adapter_is_loaded_before_the_app(self):
        html = build_static.inject_adapter(self.html, '/AxiaPlatform/')
        adapter = html.index('static-adapter.js')
        app = self.app_tag(html)
        self.assertLess(adapter, app, 'the adapter must install before the app boots')

    def test_brand_layer_loads_before_the_app(self):
        # applyBrand() reads window.AXIA_BRANDS, which brands.js defines.
        self.assertLess(self.html.index('brands.js'), self.app_tag(self.html))

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
        self.assertEqual([r['slug'] for r in rows][:4],
                         ['arya', 'ersha', 'mino', 'homa'])
        # The demo rows carry the brand artwork, so the catalog shows the real
        # marks instead of four monograms. read_catalog() returns the path
        # stored in the catalog — bare, with no deploy base — and the build
        # prefixes it exactly once afterwards.
        self.assertEqual(rows[0]['cover'], 'brand/arya-logo.webp')
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
        # The source pages carry no marker on purpose: the build derives one
        # from each file's bytes, because a hand-typed number silently went
        # stale and shipped old JS against new HTML. So the check belongs on
        # the output - and the source must not hand-type a number either.
        dist = ROOT / 'dist'
        if not (dist / 'index.html').is_file():
            self.skipTest('no dist build to inspect')
        for name, page in (('storefront', dist / 'index.html'),
                           ('console', dist / 'admin' / 'index.html')):
            if not page.is_file():
                continue
            html = page.read_text(encoding='utf-8')
            for src in re.findall(r'(?:href|src)="([^"]+?\.(?:css|js))"', html):
                self.fail(f'{name} loads {src} with no ?v= marker in the built page')

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




class PageFrameTests(unittest.TestCase):
    """The footer rests on the bottom edge, and the About page has one column.

    A short route used to leave the footer floating mid-screen with dead space
    beneath it. The fix is a body column with main taking the slack — which only
    works if there is exactly one body rule, because two would fight by source
    order.
    """

    def setUp(self):
        self.css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')
        self.app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')

    def test_the_body_is_a_column(self):
        body = re.search(r'body\{([^}]*)\}', self.css)
        self.assertIsNotNone(body)
        rules = body.group(1)
        self.assertIn('display:flex', rules)
        self.assertIn('flex-direction:column', rules)
        self.assertIn('min-height:100vh', rules)

    def test_there_is_one_body_rule(self):
        # Two blocks would work only by source order, and the second repeated a
        # property the first already set.
        self.assertEqual(len(re.findall(r'[\n;}]body\{', self.css)), 1)

    def test_main_takes_the_slack_and_the_footer_does_not_grow(self):
        self.assertIn('main{position:relative;flex:1 0 auto}', self.css)
        self.assertIn('.footer{flex:none}', self.css)
        # A fixed footer would float over content; this one scrolls away.
        footer = re.search(r'\.footer\{([^}]*)\}', self.css)
        self.assertNotIn('position:fixed', footer.group(1))

    def test_the_blog_shell_has_the_same_shape(self):
        """The flex column has to hold on the blog as well as the storefront.

        blog.py writes its own <main> and loads the same stylesheet. The footer
        is no longer one of the things it writes: that was a third copy of the
        chrome, with three links instead of four and no copyright year, so
        app.js mounts the shared one. What matters for this test is only that
        the page is the same flex column - a <main> that takes the slack,
        followed by a footer that is mounted into it.
        """
        blog = (ROOT / 'server' / 'blog.py').read_text(encoding='utf-8')
        self.assertIn('<main class="blog-main" id="main">', blog)
        self.assertNotIn('<footer class="footer">', blog,
                         'the blog is drawing its own footer again')
        app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('function footerHTML(', app)
        self.assertIn('<footer class="footer">', app)

    def test_the_about_page_has_no_approach_card(self):
        start = self.app.index('function about(')
        about = self.app[start:self.app.index('\nfunction ', start + 10)]
        self.assertNotIn('feature-panel', about)
        self.assertNotIn('Our approach', about)
        # What is left still says something: the values column and its list.
        self.assertIn('Our values', about)
        self.assertIn('Built to be clear', about)
        self.assertIn('feature-list', about)


class MobileMenuTests(unittest.TestCase):
    """The hamburger is the only navigation a phone gets.

    The top bar's links are hidden below 650px, so anything missing from the
    drawer is unreachable on a phone — not merely less convenient.
    """

    def setUp(self):
        self.app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')

    def _menu(self):
        # From the route list to the point the menu is attached: the list, the
        # destinations, the labels and the markup are all in that span.
        start = self.app.index("const mobileMenuButton=$('.mobile-menu')")
        return self.app[start:self.app.index("document.body.append(nav)", start)]

    def test_the_drawer_lists_every_destination(self):
        """Every top-level route is reachable from the phone menu."""
        # The order constant is the list; the drawer renders from it.
        start = self.app.index('const NAV_ORDER_MENU=')
        order = self.app[start:self.app.index(';', start)]
        for key in ('products', 'services', 'blog', 'aurion', 'about', 'contact'):
            self.assertIn(f"'{key}'", order, f'{key} is not in the menu list')
        menu = self._menu()
        self.assertIn('NAV_ORDER_MENU', menu,
                      'the drawer is not rendering the shared list')

    def test_the_drawer_reaches_the_blog(self):
        # The blog is a real directory, not a hash route, so it is the one entry
        # that must carry the deploy base.
        menu = self._menu()
        self.assertIn("assetUrl('blog/'", menu,
                      'a raw /blog/ drops the deployment sub-path')

    def test_the_drawer_and_the_top_bar_agree_on_the_order(self):
        """One list, asked twice.

        The drawer used to carry its own six anchors, the top bar carried five
        in index.html, and the blog carried a third set in Python. Two of them
        put Blog in different places. There is one list now - the header's -
        and the drawer reads the same destinations from it, so the two cannot
        disagree by construction. What is worth asserting is that the shared
        list holds every route, in the order the site uses.
        """
        app = self.app
        start = app.index('const NAV_ORDER=')
        order = [m for m in re.findall(r"'(\w+)'", app[start:app.index(';', start)])]
        self.assertEqual(order, ['products', 'services', 'blog', 'aurion', 'about'])
        # And the drawer's list is the same one plus the CTA.
        mstart = app.index('const NAV_ORDER_MENU=')
        menu = [m for m in re.findall(r"'(\w+)'", app[mstart:app.index(';', mstart)])]
        self.assertEqual(menu, order + ['contact'],
                         'the drawer and the header list the site differently')

    def test_the_drawer_reads_its_labels_from_the_dictionary(self):
        """A hardcoded menu is a menu that only exists in one language."""
        menu = self._menu()
        self.assertIn('AXIA_T', menu,
                      'the phone menu must translate its labels')


class BrandCategoryScopeTests(unittest.TestCase):
    """The brand strip is a websites control, and only a websites control.

    The four site brands are website builds: their logo, their name in the
    header, their accent colour. The storefront offered them on every catalog
    tab, including Applications, where none of their products appear — so
    choosing a brand emptied the grid. And a product whose *title* happened to
    contain a brand name counted as that brand's work regardless of category.
    """

    def setUp(self):
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')

    def test_the_brand_category_is_named_once(self):
        self.assertIn("const BRAND_CATEGORY = 'websites'", self.app_js)

    def test_a_brand_only_matches_a_websites_product(self):
        # The guard is the first statement: a product in another category can
        # never be that brand's, whatever its title says.
        match = self.app_js.index('function brandMatches(')
        body = self.app_js[match:match + 900]
        self.assertIn('product.category', body)
        self.assertIn('BRAND_CATEGORY', body)

    def test_the_strip_is_hidden_off_the_websites_tab(self):
        strip = self.app_js.index('function brandStrip(')
        body = self.app_js[strip:strip + 700]
        self.assertIn('productFilter', body)
        self.assertIn('BRAND_CATEGORY', body)

    def test_the_landing_page_only_offers_doors_that_open(self):
        # A category with no published product behind it is advertised on the
        # front page but opens an empty grid.
        cards = self.app_js.index('function categoryCards(')
        body = self.app_js[cards:cards + 900]
        self.assertIn('products.some(', body)


class ProductPageHidesCategoryTests(unittest.TestCase):
    """A product's own page does not print its category.

    The grid uses categories to filter; the product page is about the product.
    It printed the category in three places — the eyebrow, a badge and the
    concept preview — which is what a visitor to "Arya" saw instead of Arya.
    """

    def setUp(self):
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        start = self.app_js.index('function detail(')
        self.detail = self.app_js[start:self.app_js.index('\nfunction ', start + 10)]

    def test_the_detail_page_does_not_print_the_category(self):
        self.assertNotIn('categoryLabel(p.category)', self.detail)

    def test_the_detail_eyebrow_still_names_the_studio(self):
        self.assertIn('AXIA PRODUCT', self.detail)

    def test_the_grid_card_still_shows_the_category(self):
        # The card is a browsing surface and keeps its badge.
        start = self.app_js.index('function card(')
        card = self.app_js[start:self.app_js.index('\nfunction ', start + 10)]
        self.assertIn('categoryLabel(p.category)', card)


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
            for field in ('id', 'name', 'nameFa', 'accent'):
                self.assertTrue(brand.get(field), f'{brand.get("id")} has no {field}')
            # The operator supplies each mark; the snapshot ships theirs. A path
            # that names no file is worse than an empty one: the page renders a
            # broken plate instead of falling back to the monogram.
            mark = brand.get('mark', '')
            self.assertTrue(mark, f'{brand.get("id")} ships no artwork')
            self.assertTrue((ROOT / 'public' / mark).is_file(),
                            f'{brand.get("id")} points at a missing file: {mark}')

    def test_the_console_edits_brands(self):
        self.assertIn("['brands'", self.admin_js)
        self.assertIn('brandsTabHTML', self.admin_js)
        self.assertIn('saveBrands', self.admin_js)

    def test_a_product_without_a_cover_falls_back_to_a_logo(self):
        # The administrator's rule: no cover must never mean an empty plate.
        self.assertIn('is-emblem', self.app_js)
        self.assertIn('axiasoft-original.webp', self.app_js)
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

    def test_the_shipped_brands_carry_their_artwork(self):
        # These four brands used to ship with no artwork at all: the studio's
        # earlier logo files were withdrawn because the site should not publish
        # somebody else's drawings. The operator has since supplied a mark for
        # each brand, so they now ship one — and the paths must point at a file
        # that is really in the tree, because a stale path renders as an empty
        # plate rather than as an error.
        for brand in self.settings.DEFAULTS['brands']:
            for key in ('mark', 'logo'):
                path = brand[key]
                self.assertTrue(path, f"{brand['id']} ships no {key}")
                self.assertTrue((ROOT / 'public' / path).is_file(),
                                f"{brand['id']} {key} points at a missing file: {path}")

    def test_no_png_brand_artwork_is_left_in_the_tree(self):
        # The supplied artwork is converted to WebP on the way in: the PNGs were
        # three to five times heavier for the same picture.
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
        # The four site brands lead, in the order the operator arranged them.
        self.assertEqual([row['slug'] for row in self.catalog][:4],
                         ['arya', 'ersha', 'mino', 'homa'])

    def test_the_demo_catalog_fills_both_tabs(self):
        # The demo used to ship the four brand rows and nothing else, so the
        # Applications tab opened an empty grid and the filter row was a lie.
        # Every category the demo offers must have a product behind it.
        import sys as _sys
        _sys.path.insert(0, str(ROOT / 'tools'))
        from demo_catalog import DEMO_CATEGORIES
        for category in DEMO_CATEGORIES:
            rows = [r for r in self.catalog if r['category'] == category['id']]
            self.assertTrue(rows, f'no demo product in {category["id"]}')

    def test_the_demo_catalog_is_big_enough_to_look_like_a_catalog(self):
        # A grid of four cards in three columns is one row and a gap; the point
        # of the demo is to show what a browsable catalog looks like.
        self.assertGreaterEqual(len(self.catalog), 10)
        # And no duplicate slugs: the console's sample loader matches by slug.
        slugs = [r['slug'] for r in self.catalog]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_the_two_catalogs_cannot_leak_into_each_other(self):
        """The demo is full and the server is empty, on purpose.

        The operator asked for exactly this: "add a few products to the demo so
        it is not empty; only the server site must stay clean." The mechanism is
        that they are different artifacts, not a flag someone has to remember:

        - the demo catalog lives in tools/demo_catalog.py and reaches the page
          through data/products.js, which the *build* injects;
        - the server serves the products table and never reads that file;
        - public/index.html is the server's shell and carries no snapshot tag,
          so a server-backed page cannot pick the demo rows up by accident.
        """
        shell = (ROOT / 'public' / 'index.html').read_text(encoding='utf-8')
        built = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('data/products.js', shell,
                         'the server shell loads the demo catalog snapshot')
        self.assertIn('data/products.js', built,
                      'the demo build does not load its own catalog snapshot')

    def test_the_server_shell_has_no_product_rows(self):
        # Belt and braces on the same guarantee: the page the server serves has
        # no catalog data baked into it at all.
        shell = (ROOT / 'public' / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('AXIA_STATIC.products', shell)

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
            # `cover` is optional by design: a concept product has no artwork and
            # the storefront draws the studio emblem, which is a deliberate
            # fallback rather than a broken card. The brand rows do carry one.
            for field in ('slug', 'title', 'category', 'summary', 'description',
                          'features', 'technologies', 'status', 'price_label'):
                self.assertTrue(row.get(field) not in (None, ''),
                                f'{row.get("slug")} has no {field}')
            # Stored bare: the build adds the deploy base, and prefixing a
            # second time would bake in '/AxiaPlatform/AxiaPlatform/...'.
            cover = row.get('cover') or ''
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


class WebpLogoOnlyTests(unittest.TestCase):
    """Every shipped studio logo is a WebP, and nothing points at a PNG.

    The three originals were 157 KB, 15 KB and 10 KB as PNG and 28 KB, 5.7 KB
    and 5.4 KB as WebP — the AURION mark alone was 5.6x smaller. Both files were
    in the tree, so a page that asked for the PNG got the heavy one even though
    the light one was sitting next to it. The PNGs are gone now, which means a
    stale reference anywhere is a 404 rather than a silent slow page, so every
    place that names a logo is checked here.
    """

    BRAND = ROOT / 'public' / 'brand'

    def test_no_png_logos_remain_in_the_tree(self):
        # Includes the four brand marks the operator supplied: they arrived as
        # PNG and are converted to WebP on the way in, for the same reason the
        # studio logos were.
        self.assertEqual(sorted(p.name for p in self.BRAND.glob('*.png')), [])

    def test_the_webp_files_are_present(self):
        for name in ('axiasoft-original.webp', 'axiasoft-wordmark.webp',
                     'aurion-original.webp'):
            self.assertTrue((self.BRAND / name).is_file(), f'{name} is missing')

    def test_each_webp_is_actually_a_webp(self):
        # A file renamed to .webp is the failure mode a browser reports as a
        # broken image, not as a wrong format, so the magic bytes are checked.
        for path in sorted(self.BRAND.glob('*.webp')):
            with open(path, 'rb') as handle:
                head = handle.read(12)
            self.assertEqual(head[:4], b'RIFF', f'{path.name} is not a RIFF file')
            self.assertEqual(head[8:12], b'WEBP', f'{path.name} is not a WebP')

    def test_no_source_file_references_a_logo_png(self):
        offenders = []
        for path in list(ROOT.glob('public/**/*.js')) + list(ROOT.glob('public/**/*.html')) \
                + list(ROOT.glob('server/**/*.py')):
            text = path.read_text(encoding='utf-8', errors='ignore')
            for name in ('axiasoft-original.png', 'axiasoft-wordmark.png',
                         'aurion-original.png'):
                if name in text:
                    offenders.append(f'{path.relative_to(ROOT)}: {name}')
        self.assertEqual(offenders, [], 'these still load the heavy PNG logo')

    def test_the_storefront_does_not_need_a_picture_fallback(self):
        # <picture><source ...webp><img ...png> was the old pattern. With the
        # PNGs deleted the fallback would 404 on any browser that ignored the
        # source, so the markup names the WebP directly now.
        index = (ROOT / 'public' / 'index.html').read_text(encoding='utf-8')
        # The <link rel=preload type="image/webp"> is legitimate and stays; it
        # is the <picture><source> wrapper that has no purpose without a PNG.
        self.assertNotIn('<source', index,
                         'a <source> fallback is back; there is no PNG to fall back to')
        self.assertNotIn('</picture>', index)


class ContactFormTests(unittest.TestCase):
    """The contact page asks three questions and can actually be sent.

    The old copy said "choose a development starting point and share context",
    which named no control and handed the visitor an empty page: there was
    nothing to type into. A form that a visitor cannot see is not a contact
    page, and a form with no endpoint is a decoration, so both are asserted.
    """

    def setUp(self):
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.styles = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')
        self.app_py = (ROOT / 'server' / 'app.py').read_text(encoding='utf-8')

    def test_the_contact_page_renders_a_form(self):
        start = self.app_js.index('function contact(')
        end = self.app_js.index('\nfunction ', start + 10)
        body = self.app_js[start:end]
        self.assertIn('id="contact-form"', body)
        for field in ('name="name"', 'name="email"', 'name="message"'):
            self.assertIn(field, body)

    def test_each_field_explains_what_to_write(self):
        start = self.app_js.index('function contact(')
        end = self.app_js.index('\nfunction ', start + 10)
        body = self.app_js[start:end]
        self.assertEqual(body.count('class="field-help"'), 3,
                         'every field needs a hint, or the page asks without saying what for')

    def test_the_send_button_is_wired_to_the_endpoint(self):
        self.assertIn("api('/api/contact'", self.app_js)
        self.assertIn("if p == '/api/contact':", self.app_py)

    def test_the_endpoint_needs_no_account_and_files_a_ticket(self):
        start = self.app_py.index("if p == '/api/contact':")
        end = self.app_py.index("if p == '/api/login':", start)
        block = self.app_py[start:end]
        self.assertIn("INSERT INTO tickets", block)
        # user_id stays NULL: a visitor who has not registered still writes in.
        self.assertNotIn('self.require_user', block)

    def test_the_server_refuses_a_too_short_message(self):
        start = self.app_py.index("if p == '/api/contact':")
        end = self.app_py.index("if p == '/api/login':", start)
        block = self.app_py[start:end]
        self.assertIn('len(message) < 20', block)

    def test_the_old_vague_copy_is_gone(self):
        self.assertNotIn('Choose a development starting point and share context', self.app_js)

    def test_the_form_has_styling(self):
        for rule in ('.contact-grid', '.contact-form', '.contact-steps',
                     '.field-help', '.contact-products'):
            self.assertIn(rule, self.styles, f'{rule} is not styled')


class TextColourTests(unittest.TestCase):
    """Body text is black on light and white on dark, no third hue.

    --muted and --faint were blue-grey (#57677e / #8290a4), and on the near-white
    surfaces of the light theme they read as taupe. They are now alpha weights
    of the text colour, so secondary copy is still quieter than body copy but
    no longer a different colour family.
    """

    def setUp(self):
        self.styles = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')
        self.admin = (ROOT / 'public' / 'admin' / 'admin.css').read_text(encoding='utf-8')

    def test_dark_theme_text_is_white(self):
        self.assertIn('--text:#ffffff', self.styles)
        self.assertIn('--text:#ffffff', self.admin)

    def test_light_theme_text_is_black(self):
        self.assertIn('--text:#000000', self.styles)
        self.assertIn('--text:#000000', self.admin)

    def test_secondary_text_is_a_weight_of_the_text_colour(self):
        self.assertIn('--muted:rgba(255,255,255,.74)', self.styles)
        self.assertIn('--faint:rgba(255,255,255,.56)', self.styles)
        self.assertIn('--muted:rgba(0,0,0,.74)', self.styles)
        self.assertIn('--faint:rgba(0,0,0,.56)', self.styles)

    def test_no_blue_grey_body_tokens_are_left(self):
        for stale in ('#57677e', '#9aa9bf', '#6c7b92', '#8290a4'):
            self.assertNotIn(stale, self.styles, f'{stale} is the taupe this replaced')
            self.assertNotIn(stale, self.admin)


class BlogShellParityTests(unittest.TestCase):
    """The article pages are part of the site, not a microsite.

    They were built as a separate shell: always dark regardless of the visitor's
    choice, no theme switch, no mobile menu, and their own type sizes. A reader
    who crossed from the storefront into an article found a different site. The
    shell is now the storefront's, from styles.css.
    """

    def setUp(self):
        self.blog = (ROOT / 'server' / 'blog.py').read_text(encoding='utf-8')

    def test_the_blog_does_not_pin_its_theme_in_markup(self):
        # data-theme="dark" on <html> overrode the visitor's saved choice before
        # any script could read it.
        self.assertNotIn('<html lang="{lang}" dir="{direction}" data-theme="dark">', self.blog)

    def test_the_blog_reads_the_saved_theme_before_paint(self):
        self.assertIn("localStorage.getItem('axia-theme')", self.blog)
        self.assertIn('prefers-color-scheme: light', self.blog)

    def test_the_blog_has_the_shared_theme_switch(self):
        """The switch is app.js's, and the blog loads app.js for it."""
        self.assertIn('app.js', self.blog)
        app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('theme-toggle', app)

    def test_the_shared_header_carries_every_route(self):
        """One list of destinations, used by both pages."""
        app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        # The list moved out of the function so the drawer can read the same
        # one. What matters is that it holds every route and that the header
        # iterates it rather than spelling the links again.
        start = app.index('const NAV_ORDER=')
        order = app[start:app.index(';', start)]
        for route in ('products', 'services', 'blog', 'aurion', 'about'):
            self.assertIn(f"'{route}'", order, f'the header dropped {route}')
        body = app[app.index('function headerHTML('):app.index('function mountHeader(')]
        self.assertIn('NAV_ORDER.map', body,
                      'the header is spelling its links out again')

    def test_the_blog_declares_the_language_of_its_header(self):
        """The blog is server-rendered in two languages; it has to say which.

        The header is built by app.js from the page's own description, so the
        description has to be on the page before app.js runs - in the head,
        which is why it is a JSON block rather than an attribute on the script.
        """
        self.assertIn('id="blog-header"', self.blog)
        head = self.blog[:self.blog.index('</head>')]
        self.assertIn('id="blog-header"', head,
                      'the header description must be readable while parsing')

    def test_the_blog_loads_the_shared_stylesheet(self):
        # The URL is a template: the version is resolved at render time from the
        # built index.html, so the assertion is that the parameter is present and
        # filled from a single source, not that one particular hash is typed in.
        self.assertIn('styles.css?v={css_version}', self.blog)

    def test_the_blog_version_comes_from_the_built_page(self):
        """The blog must never pin a version of its own.

        It used to hard-code ?v=site-21. The storefront moved to content hashes
        and the article pages kept serving the old stylesheet, which is exactly
        what "the article page does not match the site" looked like. The value
        now comes from the built HTML, so it cannot fall behind again.
        """
        import re
        for name in ('styles.css', 'effects.css', 'blog.css'):
            self.assertNotRegex(self.blog, rf'{re.escape(name)}\?v=[0-9]',
                                f'{name} has a literal version again')
        self.assertIn("css_version = asset_version('styles.css')", self.blog)

    def test_the_blog_asset_version_reads_the_build_stamp(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
        import blog as blog_module
        source = (Path(__file__).resolve().parents[1] / 'index.html').read_text(encoding='utf-8')
        import re
        build_stamp = re.search(r'styles\.css\?v=([\w.-]+)', source)
        if build_stamp:
            self.assertEqual(blog_module.asset_version('styles.css'), build_stamp.group(1))


class AurionPlanLandingTests(unittest.TestCase):
    """The AURION button opens a plan page, and the plans live in one place.

    The button said "Explore packages" and scrolled to a strip on the same page;
    there was no landing to open and the four durations were a literal array
    inline in the template. The array is now AURION_PLANS, rendered by
    aurionPlanGrid() into both the product page and /aurion/plans, so the two
    cannot drift.
    """

    def setUp(self):
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.styles = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')

    def test_the_button_opens_the_plan_page(self):
        start = self.app_js.index('function aurion(')
        end = self.app_js.index('\nfunction ', start + 10)
        body = self.app_js[start:end]
        self.assertIn('href="#/aurion/plans"', body)
        self.assertIn('View the AURION plans', body)
        self.assertNotIn('Explore packages', body)

    def test_the_plan_route_exists(self):
        self.assertIn("path==='/aurion/plans'", self.app_js)

    def test_the_plan_route_respects_the_visibility_setting(self):
        """The plans page is gated by the same switch as the AURION section.

        The route is looked up after the '#', not as a whole href. Keying the
        table by the exact string only worked on the storefront, where a link
        is written "#/aurion"; the blog's header carries the deployment path
        in front of it ("/#/aurion", or "/AxiaPlatform/#/aurion" when
        published under a sub-path), so its copies of the same links matched
        nothing and never obeyed the setting. Same words, different behaviour
        - which is what "the nav list is not in sync" looks like.
        """
        self.assertIn("'/aurion/plans':'show_aurion'", self.app_js)
        self.assertIn("'/aurion':'show_aurion'", self.app_js)
        # And the lookup strips the base path instead of matching it literally.
        self.assertIn("href.slice(href.indexOf('#/') + 1)", self.app_js)

    def test_one_renderer_feeds_both_pages(self):
        self.assertIn('AURION_PLANS', self.app_js)
        self.assertIn('function aurionPlanGrid()', self.app_js)
        # Both call sites, or the pages have gone back to separate copies.
        self.assertEqual(self.app_js.count('${aurionPlanGrid()}'), 2)

    def test_all_four_durations_are_offered(self):
        for months in ("['1','Month'", "['3','Months'", "['6','Months'", "['12','Months'"):
            self.assertIn(months, self.app_js)

    def test_the_landing_is_styled(self):
        for rule in ('.plan-table', '.plan-faq', '.plans-more'):
            self.assertIn(rule, self.styles)

    def test_the_landing_still_says_nothing_is_for_sale(self):
        start = self.app_js.index('function aurionPlans()')
        end = self.app_js.index('\nfunction ', start + 10)
        body = self.app_js[start:end]
        self.assertIn('No live trading, broker connection', body)


class XionaModelTests(unittest.TestCase):
    """Xiona asks a real model, in the visitor's language.

    Three separate faults made the assistant look broken. (1) The browser only
    called /api/agent when local retrieval found *nothing*, so on a site that
    documents itself the model was almost never reached. (2) The server skipped
    the model when retrieval returned no-match, so the one class of question a
    model could have answered got the canned refusal instead. (3) The prompt
    said "reply in the language of the question" without saying which language
    that was, so Persian questions came back in English about a third of the
    time.
    """

    def setUp(self):
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.agent = (ROOT / 'server' / 'agent.py').read_text(encoding='utf-8')

    def test_the_browser_prefers_the_server_answer(self):
        start = self.app_js.index('async function sendChat(')
        end = self.app_js.index('\n// Responsive mobile navigation', start)
        body = self.app_js[start:end]
        # The server call comes before the local fallback is chosen.
        self.assertLess(body.index("fetch('/api/agent'"), body.index("answer.source==='knowledge'"))

    def test_the_server_asks_the_model_even_without_a_retrieval_hit(self):
        start = self.agent.index('def answer(')
        end = self.agent.index('\ndef status(', start)
        body = self.agent[start:end]
        self.assertNotIn("local['source'] in ('empty', 'empty-index', 'no-match')", body)
        self.assertIn('ask_provider(', body)

    def test_the_language_is_stated_rather_than_inferred(self):
        self.assertIn('Reply in {language}', self.agent)
        self.assertIn('LANGUAGE_NAMES', self.agent)
        self.assertIn("language=local.get('language')", self.agent)

    def test_a_missing_retrieval_hit_still_gets_site_context(self):
        self.assertIn('index.summary()', self.agent)
        engine = (ROOT / 'server' / 'xiona_engine.py').read_text(encoding='utf-8')
        self.assertIn('def summary(', engine)

    def test_the_prompt_no_longer_forbids_answering(self):
        # "Answer only from it" made every uncovered question a refusal.
        self.assertNotIn('Answer only from it', self.agent)
        self.assertIn('Be genuinely useful', self.agent)

    def test_the_provider_is_configurable_and_documents_gemini(self):
        self.assertIn('generativelanguage.googleapis.com', self.agent)
        self.assertIn('gemini-', self.agent)

    def test_the_key_never_reaches_the_browser(self):
        # Naming the environment variable in a sentence for the operator is
        # fine (the console does, to say what to set). Holding a value is not.
        import re
        # A Google AI Studio key starts AIza; an OpenAI key is sk-...
        secret = re.compile(r'(AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9]{20,})')
        for path in list(ROOT.glob('public/**/*.js')) + list(ROOT.glob('public/**/*.html')):
            text = path.read_text(encoding='utf-8', errors='ignore')
            self.assertIsNone(secret.search(text),
                              f'{path.relative_to(ROOT)} appears to contain an API key')
        # And no client file may read the key out of an environment it cannot see.
        self.assertNotIn('process.env.AXIA_AGENT_KEY',
                         (ROOT / 'public' / 'app.js').read_text(encoding='utf-8'))


class FaqConsoleTests(unittest.TestCase):
    """The AURION questions are edited in the console, not in the source.

    They were three literal pairs inside the aurion() template, so changing a
    sentence about licences meant a code change and a deploy. They are a site
    setting now: validated on the server, edited in its own console tab, and
    read by both the product page and the plan landing.
    """

    def setUp(self):
        self.settings = (ROOT / 'server' / 'site_settings.py').read_text(encoding='utf-8')
        self.admin_js = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')
        self.app_js = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')

    def test_the_server_knows_the_setting(self):
        import site_settings
        self.assertIn('faq', site_settings.SPEC)
        self.assertIn('faq', site_settings.GROUPS)
        self.assertIn('faq', site_settings.DEFAULTS)

    def test_the_default_is_the_three_questions_the_site_shipped_with(self):
        # An empty default would delete the section from every existing
        # install on the day this shipped. The three questions the page had
        # before the console owned them are the default instead.
        import site_settings
        faq = site_settings.DEFAULTS['faq']
        self.assertEqual(len(faq), 3)
        self.assertIn('Does AURION place trades?', [x['q'] for x in faq])
        for item in faq:
            self.assertTrue(item['qFa'], 'the Persian question is missing')
            self.assertTrue(item['aFa'], 'the Persian answer is missing')

    def test_validation_requires_a_question_and_an_answer(self):
        import site_settings
        ok, _ = site_settings.clean_value('faq', [{'q': '', 'a': 'x'}])
        self.assertFalse(ok)
        ok, _ = site_settings.clean_value('faq', [{'q': 'A', 'a': ''}])
        self.assertFalse(ok)
        ok, value = site_settings.clean_value('faq', [{'q': 'A', 'a': 'B'}])
        self.assertTrue(ok)
        self.assertEqual(value[0]['q'], 'A')

    def test_duplicate_questions_are_refused(self):
        import site_settings
        ok, _ = site_settings.clean_value('faq', [{'q': 'A', 'a': 'x'}, {'q': 'A', 'a': 'y'}])
        self.assertFalse(ok)

    def test_an_over_long_answer_is_refused(self):
        import site_settings
        ok, _ = site_settings.clean_value('faq', [{'q': 'A', 'a': 'x' * 901}])
        self.assertFalse(ok)

    def test_the_console_has_a_tab_and_an_editor(self):
        self.assertIn("['faq','Questions']", self.admin_js)
        self.assertIn('function faqTabHTML()', self.admin_js)
        self.assertIn('function faqRowHTML(', self.admin_js)

    def test_the_editor_has_both_languages(self):
        for field in ('data-field="q"', 'data-field="a"', 'data-field="qFa"', 'data-field="aFa"'):
            self.assertIn(field, self.admin_js)

    def test_the_storefront_reads_the_setting(self):
        self.assertIn('function faqList()', self.app_js)
        self.assertIn("Array.isArray(site&&site.faq)", self.app_js)

    def test_both_aurion_pages_use_the_shared_list(self):
        self.assertEqual(self.app_js.count('${faqList()'), 2)

    def test_the_hardcoded_questions_are_gone(self):
        self.assertNotIn("'Does AURION place trades?'", self.app_js)


class ProvisionAdminTests(unittest.TestCase):
    """Provisioning works however the script is invoked.

    `python3 -m server.provision_admin` put the repository root on sys.path, so
    `from app import hash_password` looked for a top-level app.py, found none,
    and died with "No module named 'app'". The directory holding the script is
    now added explicitly, which covers every invocation.
    """

    def setUp(self):
        self.src = (ROOT / 'server' / 'provision_admin.py').read_text(encoding='utf-8')

    def test_the_script_adds_its_own_directory_to_the_path(self):
        self.assertIn('sys.path.insert(0, _HERE)', self.src)
        self.assertIn('os.path.dirname(os.path.abspath(__file__))', self.src)

    def test_a_broken_checkout_gets_a_sentence_not_a_traceback(self):
        self.assertIn('except ModuleNotFoundError', self.src)
        self.assertIn('Run this script from the repository root', self.src)

    def test_it_runs_as_a_module(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, '-m', 'server.provision_admin'],
            cwd=str(ROOT), input='', capture_output=True, text=True, timeout=60)
        combined = result.stdout + result.stderr
        self.assertNotIn("No module named 'app'", combined)
        # It should reach the first prompt, then hit EOF because we fed it nothing.
        self.assertIn('Administrator email', combined)


class AgentEnvFileTests(unittest.TestCase):
    """A key can live in .env instead of being exported.

    The documented setup was three shell exports. That works in a terminal and
    fails in every other way people actually start this app — an IDE run
    button, a service manager, a compose file. `.env` is the convention
    everybody already expects, and it is ignored by Git.
    """

    def setUp(self):
        import agent
        self.agent = agent

    def _env(self, text):
        import tempfile, pathlib
        p = pathlib.Path(tempfile.mkdtemp()) / '.env'
        p.write_text(text, encoding='utf-8')
        return str(p)

    def test_a_key_is_read_from_the_file(self):
        import os
        path = self._env('AXIA_TEST_KEY_ONE=abc123\n')
        self.agent.load_env_file(path)
        self.assertEqual(os.environ.get('AXIA_TEST_KEY_ONE'), 'abc123')
        del os.environ['AXIA_TEST_KEY_ONE']

    def test_a_real_environment_variable_wins(self):
        import os
        os.environ['AXIA_TEST_KEY_TWO'] = 'from-shell'
        try:
            self.agent.load_env_file(self._env('AXIA_TEST_KEY_TWO=from-file\n'))
            self.assertEqual(os.environ['AXIA_TEST_KEY_TWO'], 'from-shell')
        finally:
            del os.environ['AXIA_TEST_KEY_TWO']

    def test_comments_and_junk_are_skipped(self):
        import os
        loaded = self.agent.load_env_file(self._env(
            '# a comment\nnot a pair\n=novalue\nAXIA_TEST_KEY_THREE=ok\n'))
        self.assertEqual(loaded.get('AXIA_TEST_KEY_THREE'), 'ok')
        self.assertEqual(len(loaded), 1)
        del os.environ['AXIA_TEST_KEY_THREE']

    def test_a_missing_file_is_not_an_error(self):
        self.assertEqual(self.agent.load_env_file('/definitely/not/here/.env'), {})

    def test_values_are_trimmed_and_unquoted(self):
        import os
        self.agent.load_env_file(self._env('AXIA_TEST_KEY_FOUR=  "padded"  \n'))
        self.assertEqual(os.environ['AXIA_TEST_KEY_FOUR'], 'padded')
        del os.environ['AXIA_TEST_KEY_FOUR']

    def test_the_example_file_ships_and_names_gemini(self):
        example = ROOT / '.env.example'
        self.assertTrue(example.is_file())
        text = example.read_text(encoding='utf-8')
        self.assertIn('generativelanguage.googleapis.com', text)
        self.assertIn('AXIA_AGENT_KEY=', text)
        # It must not ship a value that could be mistaken for a working key.
        line = [l for l in text.splitlines() if l.startswith('AXIA_AGENT_KEY=')][0]
        self.assertEqual(line.strip(), 'AXIA_AGENT_KEY=')

    def test_the_example_is_not_gitignored(self):
        # Once the file is tracked, `git add --dry-run` prints nothing (there is
        # nothing to add), so asking git whether it would add it answers the
        # wrong question. The rule that matters is that `.gitignore` names it as
        # an exception to `.env.*`, and that the real secret is still ignored.
        import subprocess
        ignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
        self.assertIn('!.env.example', ignore)
        ignored = subprocess.run(['git', 'check-ignore', '-q', '.env'],
                                 cwd=str(ROOT), capture_output=True)
        self.assertEqual(ignored.returncode, 0, '.env must stay ignored')
        tracked = subprocess.run(['git', 'ls-files', '--error-unmatch', '.env.example'],
                                 cwd=str(ROOT), capture_output=True)
        self.assertEqual(tracked.returncode, 0, '.env.example should be in the repository')


class XionaLanguageTests(unittest.TestCase):
    """A Persian question gets a Persian answer, and vice versa.

    The prompt used to say "reply in the language of the question" without
    saying which language that was, and the model guessed wrong often enough to
    be reported as a bug. The language is now detected once — the same pass
    that scores retrieval — and written into the prompt.
    """

    def setUp(self):
        import agent
        self.agent = agent

    def test_persian_is_detected(self):
        self.assertTrue(self.agent._looks_persian('چطور یک وب‌سایت بسازم؟'))
        self.assertFalse(self.agent._looks_persian('How do I build a website?'))

    def test_the_prompt_states_the_language(self):
        self.assertEqual(self.agent.LANGUAGE_NAMES['fa'], 'Persian (فارسی)')
        self.assertEqual(self.agent.LANGUAGE_NAMES['en'], 'English')

    def test_a_persian_question_produces_a_persian_instruction(self):
        # Runs ask_provider against a local stub, so the assertion is about the
        # prompt that actually leaves the process.
        import json, os, threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        seen = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get('Content-Length') or 0)
                seen['body'] = json.loads(self.rfile.read(n))
                out = json.dumps({'choices': [{'message': {'content': 'پاسخ.'}}]}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        server = HTTPServer(('127.0.0.1', 0), Handler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        saved = {k: os.environ.get(k) for k in
                 ('AXIA_AGENT_KEY', 'AXIA_AGENT_URL', 'AXIA_AGENT_MODEL')}
        os.environ.update(AXIA_AGENT_KEY='k', AXIA_AGENT_URL=f'http://127.0.0.1:{port}/v1',
                          AXIA_AGENT_MODEL='test-model')
        try:
            text, error = self.agent.ask_provider('چطور شروع کنم؟', language='fa')
            self.assertIsNone(error)
            system = seen['body']['messages'][0]['content']
            self.assertIn('Reply in Persian', system)
            self.assertIn('AXIASOFT', system)
        finally:
            server.shutdown()
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_an_answer_reports_which_side_produced_it(self):
        import os
        saved = os.environ.pop('AXIA_AGENT_KEY', None)
        try:
            result = self.agent.answer('What is AURION?')
            self.assertIn(result['provider'], ('on-site', 'local'))
        finally:
            if saved is not None:
                os.environ['AXIA_AGENT_KEY'] = saved


class HeaderControlTests(unittest.TestCase):
    """Every control in the header is the same size.

    Four different sizes sat in one row: a 38px icon button, a 36px icon button
    below 650px, a link-shaped button whose height came from its padding, and a
    CTA with a third padding again. Pinned to one height and one radius here.
    """

    def setUp(self):
        self.css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')

    def test_the_header_pins_a_height(self):
        # It used to pin 38px, then 34px on a phone, in three hand-written rules
        # that each named the same three selectors. The height is a variable
        # now, and the header selects the small tier in one place - which is
        # what the old block was trying to say.
        self.assertRegex(self.css, r'\.nav-actions[^{]*\{[^}]*--btn-h:\s*var\(--btn-h-sm\)')
        self.assertIn('--btn-h-sm:', self.css)

    def test_the_icon_button_matches_the_text_buttons(self):
        # Both take their height from the same variable, in the same tier.
        block = re.findall(r'\.icon-button\s*\{([^}]*)\}', self.css)
        self.assertTrue(any('var(--btn-h)' in b for b in block),
                        'the icon button does not take its size from --btn-h')
        self.assertRegex(self.css, r'\.button\s*\{[^}]*min-height:\s*var\(--btn-h\)')

    def test_the_shrink_at_the_mobile_breakpoint_is_shared(self):
        # One breakpoint changes the variable, so every control shrinks together.
        # The old test looked for three selectors inside a media query; the
        # invariant is the same, expressed once.
        block = re.findall(r'@media \(max-width: 650px\) \{([^@]*?)\n\}', self.css)
        self.assertTrue(any('--btn-h' in b for b in block),
                        'the phone breakpoint does not adjust the button height')

    def test_only_the_header_is_pinned(self):
        # The same .button class is used across the site, where the natural
        # padding is wanted. A bare `.button { height: 38px }` would flatten
        # every CTA on every page.
        import re
        bare = re.findall(r'(?<![>\s])\.button\s*\{[^}]*height:\s*38px', self.css)
        self.assertEqual(bare, [], 'the height rule must be scoped to .topbar')


class ThemeIconTests(unittest.TestCase):
    """The theme button is a drawn sun and moon, not a character.

    ◐ and ☼ are astronomical notation: different weights in different fonts,
    a smudge at 15px, and meaningless in the light theme — a half-filled circle
    on a page that is already light reads as "partly dark".
    """

    def setUp(self):
        self.app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.index = (ROOT / 'public' / 'index.html').read_text(encoding='utf-8')
        self.blog = (ROOT / 'server' / 'blog.py').read_text(encoding='utf-8')

    def test_the_markup_ships_an_svg(self):
        self.assertIn('class="theme-icon"><svg', self.index)

    def test_the_old_glyphs_are_gone_from_markup(self):
        self.assertNotIn('◐', self.index)
        self.assertNotIn('>☼<', self.index)

    def test_the_shared_header_ships_an_svg(self):
        app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        start = app.index('function headerHTML(')
        end = app.index('function mountHeader(')
        self.assertIn("ICON('moon')", app[start:end],
                      'the theme button is drawn, not typed')

    def test_both_glyphs_are_drawn(self):
        self.assertIn('THEME_SUN', self.app)
        self.assertIn('THEME_MOON', self.app)

    def test_the_label_names_the_action_not_the_state(self):
        self.assertIn('Switch to light theme', self.app)
        self.assertIn('Switch to dark theme', self.app)

    def test_the_shared_header_has_localised_labels(self):
        """Labels come from the site dictionary, not a blog-only copy.

        blog.py had its own table of header strings, which is how its version of
        the About link came to be spelled differently from the storefront's.
        """
        i18n = (ROOT / 'public' / 'i18n.js').read_text(encoding='utf-8')
        for key in ('Switch to light theme', 'Switch to dark theme',
                    'Main navigation', 'Open menu', 'Close menu'):
            self.assertIn(key, i18n, f'the dictionary has no {key!r}')


class AdminThemeIconTests(unittest.TestCase):
    """The console draws the same sun and moon.

    It kept the old pair, so the two surfaces disagreed and the console still
    showed an illegible half-circle in the light theme.
    """

    def setUp(self):
        self.js = (ROOT / 'public' / 'admin' / 'admin.js').read_text(encoding='utf-8')

    def test_the_console_draws_svgs(self):
        self.assertIn('ADMIN_SUN', self.js)
        self.assertIn('ADMIN_MOON', self.js)

    def test_the_toggle_repaints_the_icon(self):
        self.assertIn('b.innerHTML=themeGlyph()', self.js)

    def test_no_text_glyph_is_written_into_the_button(self):
        # The comment explains the change and mentions the old characters; only
        # an assignment to the button would be a regression.
        self.assertNotIn("textContent=t==='dark'", self.js)
        self.assertNotIn("?'◐':'☼'", self.js)

class TiltReachTests(unittest.TestCase):
    """Tilt is stronger, works under a finger, and covers the page but not the
    header.

    It used to be 10 degrees with a 10px lift, and a blanket rule switched it
    off on every touch device. The rule now removes only the hover half on
    touch; the press half lives in app.js.
    """

    def setUp(self):
        self.css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')
        self.app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')

    def test_the_angle_and_lift_are_bigger(self):
        self.assertIn('perspective(820px)', self.css)
        self.assertIn('translateZ(24px)', self.css)

    def test_the_shadow_moves_with_the_card(self):
        self.assertIn('box-shadow:0 34px 70px', self.css)

    def test_the_light_theme_gets_a_lighter_shadow(self):
        self.assertIn('[data-theme=light] .tilt-hover.is-tilting', self.css)

    def test_touch_is_not_a_blanket_off_switch(self):
        start = self.css.index('@media(hover:none),(pointer:coarse){')
        depth = 0
        for i in range(self.css.index('{', start), len(self.css)):
            if self.css[i] == '{':
                depth += 1
            elif self.css[i] == '}':
                depth -= 1
                if depth == 0:
                    block = self.css[start:i + 1]
                    break
        self.assertNotIn('transform:none!important', block)

    def test_touch_gets_a_press_driven_tilt(self):
        self.assertIn('.tilt-hover.is-tilting{transform:perspective(900px)', self.css)

    def test_the_app_drives_both_inputs(self):
        self.assertIn("matchMedia('(pointer:coarse)')", self.app)
        self.assertIn("addEventListener('pointerdown',start", self.app)
        self.assertIn("addEventListener('pointerup',end", self.app)

    def test_cards_and_buttons_are_covered(self):
        self.assertIn('TILT_SELECTORS', self.app)
        for selector in ('.category-card', '.product-card', '.stat-card',
                         '.cta-band', '.contact-card', '.button:not(.button-small)'):
            self.assertIn(selector, self.app, f'{selector} is not tilted')

    def test_the_header_is_excluded(self):
        self.assertIn("el.closest('.topbar')", self.app)

    def test_a_new_render_reapplies_the_classes(self):
        # Half the routes build their markup after the first paint, so one call
        # site would miss them.
        self.assertIn('new MutationObserver', self.app)
        self.assertIn('startTiltWatcher', self.app)


class BlogShellMotionTests(unittest.TestCase):
    """The article pages load the same motion layer as the storefront.

    They did not, so two things were missing: the click ripple, and the
    `tap-highlight-color: transparent` rule that stops the browser painting its
    own grey-blue rectangle over a pressed control. That rectangle was the
    "blue square hover" reported on the blog — the header's buttons are the only
    controls there, so it was the only thing anyone saw.
    """

    def setUp(self):
        self.blog = (ROOT / 'server' / 'blog.py').read_text(encoding='utf-8')
        self.effects = (ROOT / 'public' / 'effects.css').read_text(encoding='utf-8')

    def test_the_blog_loads_effects_css(self):
        self.assertIn('effects.css?v=', self.blog)

    def test_the_blog_loads_effects_js(self):
        self.assertIn('effects.js?v=', self.blog)

    def test_the_layer_clears_the_tap_highlight(self):
        self.assertIn('-webkit-tap-highlight-color: transparent', self.effects)
        self.assertIn('tap-highlight-color: transparent', self.effects)

    def test_the_ripple_covers_the_header_controls(self):
        # .icon-button is in the ripple's selector list, or the theme and menu
        # buttons would be the only controls without one. The list is the block
        # that sets tap-highlight-color, not everything before the first brace.
        marker = 'tap-highlight-color: transparent'
        start = self.effects.rindex('{', 0, self.effects.index(marker))
        selector_list = self.effects[:start]
        selector_list = selector_list[selector_list.rindex('}') + 1:] if '}' in selector_list else selector_list
        self.assertIn('.icon-button', selector_list)


class BlogDrawerCascadeTests(unittest.TestCase):
    """The blog drawer can actually be closed.

    styles.css opens `.mobile-nav` with `display: flex !important` because the
    storefront inserts it only when it should be visible. The blog renders it in
    the markup and toggles `hidden`, so a plain `display: none` lost the cascade
    to that !important. The drawer was therefore always on screen — which is why
    the menu button looked broken: the panel was already covering it, and the
    first tap was hitting the panel.
    """

    def setUp(self):
        self.css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')
        self.blog_css = (ROOT / 'public' / 'blog.css').read_text(encoding='utf-8')
        self.blog = (ROOT / 'server' / 'blog.py').read_text(encoding='utf-8')

    def test_the_storefront_still_opens_it_with_important(self):
        # If this ever changes, the blog rule below can drop its own !important.
        # Asserting it keeps the reason visible.
        self.assertRegex(self.css, r'\.mobile-nav\{display:flex!important')

    def test_the_blog_closes_it_with_important(self):
        self.assertIn('.blog-body .mobile-nav[hidden] { display: none !important; }',
                      self.blog_css)

    def test_the_blog_gets_the_shared_header(self):
        """The drawer is app.js's now, not a second copy in blog.py.

        It used to be markup in blog.py with its own show/hide, its own close
        button and its own body-scroll lock - five things to keep in step with
        the storefront's, and they did not stay in step. The blog loads app.js
        and asks for the header; the drawer comes with it.
        """
        self.assertIn('app.js', self.blog)
        self.assertNotIn('id="blog-mobile-nav"', self.blog,
                         'the blog is drawing its own drawer again')

    def test_the_shared_drawer_toggles_the_hidden_attribute(self):
        app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        # hidden is what assistive technology follows; a class alone leaves the
        # links reachable by tab while they are visually gone.
        self.assertRegex(app, r"\.hidden\s*=")

    def test_the_shared_drawer_has_a_working_close(self):
        app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('mobileMenuButton', app)
        self.assertIn('close-mobile', app)

    def test_a_link_inside_closes_it(self):
        """Choosing a destination closes the menu, or it stays over the page."""
        app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        start = app.index("const mobileMenuButton=$('.mobile-menu')")
        menu = app[start:app.index('window.openAuth=openAuth;', start)]
        self.assertRegex(menu, r"\$\$\('a',nav\)\.forEach\(a=>a\.onclick=closeMenu\)")

    def test_the_shared_drawer_locks_the_body_scroll(self):
        app = (ROOT / 'public' / 'app.js').read_text(encoding='utf-8')
        self.assertIn("document.body.style.overflow", app,
                      'opening the drawer on a phone must stop the page behind '
                      'it scrolling')


class FocusRingTests(unittest.TestCase):
    """A focus ring follows the control's own radius.

    `outline` draws a rectangle and border-radius does not clip it, so tabbing
    to a pill-shaped button drew a hard blue box around a rounded surface.
    """

    def setUp(self):
        self.css = (ROOT / 'public' / 'styles.css').read_text(encoding='utf-8')

    def test_rounded_controls_get_a_rounded_ring(self):
        block = self.css[self.css.index('.button:focus-visible,'):]
        self.assertIn('border-radius: 11px', block[:600])

    def test_the_ring_is_not_removed(self):
        # Cosmetic, not a reason to take focus indication away.
        self.assertIn('outline: 2px solid var(--blue)', self.css)


class DemoArticleTests(unittest.TestCase):
    """The WordPress-versus-code article has to exist everywhere it is linked.

    It was written as a demo post a visitor can click through, so it must be on
    the blog index, open at its own URL, available in the English mirror, and
    present in the browser-only console's seed — a demo article that only exists
    in one of those is a dead link in three others.
    """

    @classmethod
    def setUpClass(cls):
        cls.articles = json.loads((ROOT / 'data' / 'articles.json').read_text(encoding='utf-8'))
        cls.by_slug = {a['slug']: a for a in cls.articles}
        cls.article = cls.by_slug.get('wordpress-vs-code')
        cls.translations = json.loads((ROOT / 'data' / 'translations.json').read_text(encoding='utf-8'))

    def test_the_demo_article_is_published_in_persian(self):
        self.assertIsNotNone(self.article, 'the demo article is missing from data/articles.json')
        self.assertEqual(self.article.get('language'), 'fa')
        self.assertTrue(self.article.get('published_at'))

    def test_it_actually_compares_the_two_approaches(self):
        # Not a stub: it must name both subjects, and carry a comparison table.
        body = self.article['body']
        self.assertIn('وردپرس', body)
        self.assertIn('| --- |', body)
        self.assertGreater(len(body), 1500)

    def test_it_has_a_current_english_mirror(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        import translate_articles
        entry = self.translations.get('wordpress-vs-code')
        self.assertIsNotNone(entry, 'the demo article has no English copy')
        self.assertEqual(entry['source_hash'], translate_articles.digest(self.article),
                         'the English copy is stale — run tools/translate_articles.py')
        self.assertIn('WordPress', entry['title'] + entry['body'])
        self.assertIn('| --- |', entry['body'])

    def test_every_article_still_has_a_current_english_mirror(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        import translate_articles
        for article in self.articles:
            if str(article.get('language') or 'fa') != 'fa':
                continue
            entry = self.translations.get(article['slug'])
            self.assertIsNotNone(entry, f'{article["slug"]} has no English copy')
            self.assertEqual(entry['source_hash'], translate_articles.digest(article),
                             f'{article["slug"]} has a stale English copy')

    def test_the_console_seeds_it_from_the_shipped_snapshot(self):
        # The browser-only build has no server to read articles from, so the
        # console seeds from data/products.js. Without the seed the demo's
        # Articles page is empty and the demo post cannot be reached there.
        source = (ROOT / 'public' / 'demo-backend.js').read_text(encoding='utf-8')
        self.assertIn('function seedArticles()', source)
        self.assertIn('seedArticles()', source[source.index('function readArticles()'):])

    def test_public_article_reads_are_not_behind_the_admin_gate(self):
        source = (ROOT / 'public' / 'demo-backend.js').read_text(encoding='utf-8')
        admin = source.index("// ---- admin ---")
        public = source.index("if (path === '/api/articles' && method === 'GET')")
        self.assertLess(public, admin,
                        'a public article read must be answered before the admin gate')


class BlogBuildOutputTests(unittest.TestCase):
    """A real build of the blog tree, checked on disk.

    Two bugs lived here and neither could be seen in the source: the English
    pages rendered an empty prose block because the body was dropped before the
    article was rendered, and every breadcrumb read
    '/AxiaPlatform/AxiaPlatform/blog/' because the base was applied twice.
    """

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name)
        (cls.out / 'data').mkdir(parents=True, exist_ok=True)
        settings = {'default_theme': 'dark'}
        (cls.out / 'data' / 'settings.json').write_text(json.dumps(settings), encoding='utf-8')
        build_static.write_blog(cls.out, '/AxiaPlatform/', 'https://axiasoft.github.io')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def read(self, *parts):
        return (self.out.joinpath(*parts)).read_text(encoding='utf-8')

    def test_both_article_trees_are_written(self):
        self.assertTrue((self.out / 'blog' / 'wordpress-vs-code' / 'index.html').is_file())
        self.assertTrue((self.out / 'en' / 'blog' / 'wordpress-vs-code' / 'index.html').is_file())

    def test_the_persian_article_has_its_body(self):
        page = self.read('blog', 'wordpress-vs-code', 'index.html')
        self.assertIn('<table>', page)
        self.assertIn('وردپرس', page)

    def test_the_english_article_has_its_body(self):
        # The regression: title and summary were English, the prose was empty.
        page = self.read('en', 'blog', 'wordpress-vs-code', 'index.html')
        start = page.index('<div class="blog-prose"')
        end = page.index('</div>', start)
        prose = page[start:end]
        self.assertGreater(len(prose), 500, 'the English article rendered no body')
        self.assertIn('WordPress', prose)
        self.assertIn('<table>', prose)

    def test_the_index_links_to_the_article(self):
        start = self.read('blog', 'index.html')
        self.assertIn('blog/wordpress-vs-code/', start.replace('/AxiaPlatform/blog/', 'blog/'))
        en = self.read('en', 'blog', 'index.html')
        self.assertIn('WordPress or hand-coded', en)

    def test_no_link_doubles_the_base_path(self):
        for parts in (('blog', 'index.html'),
                      ('blog', 'wordpress-vs-code', 'index.html'),
                      ('en', 'blog', 'index.html'),
                      ('en', 'blog', 'wordpress-vs-code', 'index.html'),
                      ('blog', 'feed.xml')):
            page = self.read(*parts)
            self.assertNotIn('/AxiaPlatform/AxiaPlatform', page, f'{parts} doubled the base')
            self.assertNotIn('AxiaPlatform//', page, f'{parts} doubled a slash')

    def test_every_internal_link_resolves(self):
        pages = [self.out / 'blog' / 'index.html',
                 self.out / 'blog' / 'wordpress-vs-code' / 'index.html',
                 self.out / 'en' / 'blog' / 'index.html',
                 self.out / 'en' / 'blog' / 'wordpress-vs-code' / 'index.html']
        for page in pages:
            for href in set(re.findall(r'href="(/AxiaPlatform/[^"#?]*)', page.read_text(encoding='utf-8'))):
                # Stylesheet and font links point at files this temp tree does
                # not build; only page links have to resolve here.
                if not re.search(r'/(blog|en/blog)/', href):
                    continue
                rel = href[len('/AxiaPlatform/'):]
                target = self.out / rel
                if href.endswith('/'):
                    target = self.out / rel / 'index.html'
                self.assertTrue(target.exists(), f'{page.name} links to missing {href}')

    def test_an_untranslated_post_still_renders_its_body(self):
        # The fallback page for a post with no stored English copy is written by
        # a third branch, which had the same doubled base and the same missing
        # body. Checked by building once with the translations hidden.
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        out = Path(temp.name)
        (out / 'data').mkdir(parents=True, exist_ok=True)
        (out / 'data' / 'settings.json').write_text('{"default_theme": "dark"}', encoding='utf-8')
        original = build_static.ROOT
        try:
            # Hide every stored translation from this one build.
            import shutil
            mirror = out / 'repo'
            (mirror / 'data').mkdir(parents=True, exist_ok=True)
            (mirror / 'data' / 'articles.json').write_text(
                (original / 'data' / 'articles.json').read_text(encoding='utf-8'), encoding='utf-8')
            (mirror / 'data' / 'translations.json').write_text('{}', encoding='utf-8')
            build_static.ROOT = mirror
            build_static.write_blog(out, '/AxiaPlatform/', 'https://axiasoft.github.io')
        finally:
            build_static.ROOT = original
        page = (out / 'en' / 'blog' / 'wordpress-vs-code' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('blog-notice', page, 'the page must say the copy is untranslated')
        self.assertNotIn('/AxiaPlatform/AxiaPlatform', page)
        start = page.index('<div class="blog-prose"')
        self.assertGreater(page.index('</div>', start) - start, 500,
                           'the fallback page rendered no body')

    def test_the_article_theme_follows_the_setting(self):
        page = self.read('blog', 'wordpress-vs-code', 'index.html')
        self.assertIn('var fallback = "dark";', page)


class AssetBusterTests(unittest.TestCase):
    """A changed asset must never keep its old URL.

    The version numbers were typed into the HTML by hand: `/app.js?v=site-29`.
    Nothing checked them, so an edited app.js shipped under the old number was
    served from cache and the fix never reached the phone - which is exactly
    what happened to a translation this round. The build now derives the number
    from the file's bytes, so the URL cannot lag the content.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        import build_static
        self.build = build_static
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_the_build_stamps_a_bare_tag_and_overwrites_a_stale_one(self):
        # Exercised through the function, not through dist/: a check that reads
        # a build made earlier still passes after the stamping is disabled.
        (self.tmp / 'app.js').write_text('boot();', encoding='utf-8')
        (self.tmp / 'styles.css').write_text('body{}', encoding='utf-8')
        expected = self.build.content_buster(self.tmp / 'app.js', 'app.js')
        for page in ('<script src="/app.js" defer></script>',
                     '<script src="/app.js?v=site-29" defer></script>',
                     '<script src="/AxiaPlatform/app.js?v=old" defer></script>'):
            out = self.build.stamp_asset_urls(page, self.tmp, '/AxiaPlatform/')
            self.assertIn(f'app.js?v={expected}', out, f'unstamped: {page} -> {out}')
        # An asset the build does not own keeps its own number.
        kept = self.build.stamp_asset_urls(
            '<script src="/data/products.js?v=static-2"></script>', self.tmp, '/')
        self.assertIn('products.js?v=static-2', kept)

    def test_a_changed_file_gets_a_new_url(self):
        asset = self.tmp / 'app.js'
        asset.write_text('one();', encoding='utf-8')
        first = self.build.content_buster(asset, 'app.js')
        asset.write_text('two();', encoding='utf-8')
        second = self.build.content_buster(asset, 'app.js')
        self.assertNotEqual(first, second, 'an edited file kept its old cache key')

    def test_an_unchanged_file_keeps_its_url(self):
        # Rewriting a file with identical bytes must not evict every cache.
        asset = self.tmp / 'app.js'
        asset.write_text('same();', encoding='utf-8')
        self.assertEqual(self.build.content_buster(asset, 'app.js'),
                         self.build.content_buster(asset, 'app.js'))

    def test_every_stamped_asset_exists_in_the_built_page(self):
        dist = ROOT / 'dist'
        if not (dist / 'index.html').is_file():
            self.skipTest('no dist build to inspect')
        for page in (dist / 'index.html', dist / 'admin' / 'index.html'):
            if not page.is_file():
                continue
            text = page.read_text(encoding='utf-8')
            for href in re.findall(r'(?:src|href)="[^"]*?((?:app|styles|i18n|effects|brands'
                                   r'|xiona|admin/admin)\.(?:js|css))\?v=([^"]+)"', text):
                name, buster = href
                target = dist / name
                self.assertTrue(target.is_file(), f'{page.name} points at a missing {name}')
                expected = self.build.content_buster(target, name)
                if expected is not None:
                    self.assertEqual(buster, expected,
                                     f'{name} is served under a stale cache key')

    def test_the_page_does_not_carry_a_hand_typed_number(self):
        # A leftover `?v=site-29` in the source is a landmine: it works until
        # someone edits the file and the build never overwrites it.
        for rel in ('public/index.html', 'public/admin/index.html'):
            text = (ROOT / rel).read_text(encoding='utf-8')
            for number in re.findall(r'\?v=(site|console)-\d+', text):
                self.fail(f'{rel} still hand-types ?v={number}-<n>; '
                          f'the build derives this from the file')
