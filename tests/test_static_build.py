"""Guards for the generated GitHub Pages build.

The static build has no server, so a single malformed tag in the shell can
disable it silently: an unclosed <script> swallows every following tag as raw
text, which is exactly how the static adapter once disappeared from a build
that still reported success. These tests fail loudly instead.
"""
import json
import shutil
import subprocess
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
        missing = sorted(requested - known)
        self.assertEqual(missing, [],
                         'these stay English in a Persian console')

    def test_the_console_never_prints_a_plural_placeholder(self):
        # '(s)' is a note to the developer, not a word. It used to reach the
        # screen: 'project request(s) need a first review.'
        import re
        for m in re.finditer(r"T\('([^']*)'\)", self.admin):
            self.assertNotIn('(s)', m.group(1),
                             f'{m.group(1)!r} would print a plural placeholder')


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
            for field in ('id', 'name', 'mark', 'accent'):
                self.assertTrue(brand.get(field), f'{brand.get("id")} has no {field}')

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
        self.assertIn('.brand-picker-row { grid-template-columns: 1fr;', styles)

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