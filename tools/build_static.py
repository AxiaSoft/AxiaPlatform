"""Build a static, GitHub Pages ready version of the AXIASOFT site.

GitHub Pages cannot run Python, so this script exports the public interface as
static files while keeping the real API-driven version intact for the Python
server. Everything it emits is generated; do not edit the output by hand.

What it does
------------
1. Copies ``public/`` into ``dist/`` under the repository's Pages sub-path
   (``/AxiaPlatform/`` for a project site, ``/`` for a user or custom-domain
   site) and rewrites the root-absolute asset, link and font URLs.
2. Reads the published catalog from the SQLite database (or the seed data) and
   writes ``dist/data/products.json`` plus a snapshot file
   ``dist/data/products.js`` that is loaded with a normal script tag. The
   snapshot lets the catalog render even if ``fetch`` is blocked.
3. Injects ``public/static-adapter.js`` ahead of the app so that the client-side
   contracts the app expects (``/api/products``, ``/api/me``) are answered
   locally, and account/order/cart actions explain that they need the live
   server instead of failing silently.
4. Adds ``.nojekyll``, rewrites ``sitemap.xml`` and ``robots.txt`` for the real
   Pages origin, and writes ``404.html`` with the correct base path.

Usage
-----
    python3 tools/build_static.py                       # -> dist/
    python3 tools/build_static.py --base /AxiaPlatform/ # project site (default)
    python3 tools/build_static.py --base /              # user site / custom domain
    python3 tools/build_static.py --origin https://axiasoft.github.io
    python3 tools/build_static.py --demo                # hide order buttons too

The script is deterministic: running it twice with the same database produces
byte-identical output apart from ``data/snapshot-meta.js``.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'
DIST = ROOT / 'dist'

TEXT_SUFFIXES = {'.html', '.css', '.js', '.xml', '.txt', '.webmanifest', '.json', '.svg'}
OVERRIDES = ROOT / 'tools' / 'static-overrides'
# Files served by the server build but meaningless (or misleading) when static.
# static-config.js is generated below, never copied. The admin console is copied
# too: GitHub Pages builds serve it backed by public/demo-backend.js.
STATIC_OMIT = {'static-config.js'}

# Root-relative references that must become base-aware. Bindings and protocol
# URLs are handled separately so "//" sequences are never touched.
REFERENCE_RE = re.compile(r'(?<![\w:/.\\])(href|src|action|content)="(/[^/"][^"]*)"')
# `url(/fonts/...)` inside CSS (and inline styles) points at the origin root, so it
# also has to follow the Pages base path. Without this the @font-face 404s and the
# Persian text renders in a wider fallback font.
CSS_URL_RE = re.compile(r'(url\(\s*[\'"]?)(/[^/\'")\s][^\'")\s]*)')

SITEMAP_ROUTES = [
    ('', 'weekly', '1.0'),
    ('#/products', 'weekly', '0.9'),
    ('#/services', 'monthly', '0.8'),
    ('#/aurion', 'monthly', '0.7'),
    ('#/about', 'monthly', '0.6'),
    ('#/contact', 'monthly', '0.8'),
    ('#/privacy', 'yearly', '0.3'),
    ('#/terms', 'yearly', '0.3'),
    ('#/refunds-policy', 'yearly', '0.3'),
]

# The adapter must be registered before app.js, so it is inserted immediately
# before the app bundle's script tag.
def app_script_re(base: str) -> re.Pattern:
    return re.compile(r'(\s*)<script src="' + re.escape(base) + r'app\.js[^"]*" defer></script>')


def read_catalog(db_path: Path) -> list[dict]:
    """Return published products, falling back to the bundled seed data."""
    rows: list[dict] = []
    if db_path.is_file():
        try:
            conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
            conn.row_factory = sqlite3.Row
            try:
                rows = [
                    dict(r) for r in conn.execute(
                        'SELECT id,slug,title,category,summary,description,cover,features,'
                        'technologies,status,price_label,published,created_at '
                        'FROM products WHERE published=1 ORDER BY id')
                ]
            finally:
                conn.close()
        except sqlite3.Error as exc:
            print(f'  database not readable ({exc}); using seed catalog', file=sys.stderr)
    if not rows:
        try:
            sys.path.insert(0, str(ROOT / 'server'))
            import db as server_db  # noqa: WPS433 (deliberate late import)
            seeds = server_db.SEED_PRODUCTS
        except Exception:
            seeds = []
        for index, seed in enumerate(seeds, start=1):
            slug, title, category, summary, description, cover, features, tech, status, price = seed
            rows.append({
                'id': index, 'slug': slug, 'title': title, 'category': category,
                'summary': summary, 'description': description, 'cover': cover,
                'features': features, 'technologies': tech, 'status': status,
                'price_label': price, 'published': 1, 'created_at': '',
            })
    for row in rows:
        for field in ('features', 'technologies'):
            value = row.get(field)
            if isinstance(value, str):
                try:
                    row[field] = json.loads(value)
                except json.JSONDecodeError:
                    row[field] = []
        row['published'] = 1
    return rows


def rewrite_references(text: str, base: str) -> str:
    """Prefix root-absolute asset/link references with the Pages base path."""
    if base == '/':
        return text

    def replace(match: re.Match) -> str:
        attr, target = match.group(1), match.group(2)
        if target.startswith(base) or target.startswith('//'):
            return match.group(0)
        return f'{attr}="{base}{target.lstrip("/")}"'

    text = REFERENCE_RE.sub(replace, text)

    def replace_url(match: re.Match) -> str:
        lead, target = match.group(1), match.group(2)
        if target.startswith(base):
            return match.group(0)
        return f'{lead}{base}{target.lstrip("/")}'

    return CSS_URL_RE.sub(replace_url, text)


def build_sitemap(origin: str, base: str) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for route, freq, priority in SITEMAP_ROUTES:
        lines.append(f'  <url><loc>{origin}{base}{route}</loc>'
                     f'<changefreq>{freq}</changefreq><priority>{priority}</priority></url>')
    lines.append('</urlset>')
    return '\n'.join(lines) + '\n'


def build_robots(origin: str, base: str) -> str:
    return (
        '# AXIASOFT — crawler policy (static GitHub Pages build)\n'
        'User-agent: *\n'
        'Allow: /\n'
        'Disallow: /admin/\n'
        f'\nSitemap: {origin}{base}sitemap.xml\n'
    )


def build_404(base: str) -> str:
    """Return the 404 page with base-aware links so it works under a sub-path."""
    source = PUBLIC / '404.html'
    if not source.is_file():
        return f'<!doctype html><title>Not found</title><a href="{base}">Return home</a>'
    return rewrite_references(source.read_text(encoding='utf-8'), base)


def inject_adapter(html: str, base: str) -> str:
    """Insert the static adapter just before the app bundle."""
    tag = f'<script src="{base}static-adapter.js?v=static-1" defer></script>'
    if 'static-adapter.js' in html:
        return html
    match = app_script_re(base).search(html)
    if match:
        return html[:match.start()] + match.group(1) + tag + html[match.start():]
    # Fall back to the end of the body so the adapter still runs.
    return html.replace('</body>', f'  {tag}\n</body>')


def static_html(index_html: str, base: str) -> str:
    """Turn the SPA shell into a page that stays honest about the static build."""
    html = index_html
    # The build has no administrator login; point that entry at the note page.
    html = html.replace('<script src="{base}app.js', '<script src="{base}app.js')
    return html


def main() -> int:
    parser = argparse.ArgumentParser(description='Build the static GitHub Pages site.')
    parser.add_argument('--base', default='/AxiaPlatform/',
                        help='Pages sub-path, e.g. /AxiaPlatform/ or / (default: /AxiaPlatform/)')
    parser.add_argument('--origin', default='https://axiasoft.github.io',
                        help='Site origin used in sitemap/robots (default: https://axiasoft.github.io)')
    parser.add_argument('--db', default=str(ROOT / 'data' / 'axiasoft.sqlite3'),
                        help='SQLite database to read the catalog from')
    parser.add_argument('--out', default=str(DIST), help='Output directory (default: dist/)')
    parser.add_argument('--demo', action='store_true',
                        help='Also hide project-request buttons (pure catalog demo)')
    parser.add_argument('--clean', action='store_true',
                        help='Delete the output directory before writing. Only needed when '
                             'the directory holds stale files (e.g. both docs/ and a root build).')
    args = parser.parse_args()

    base = '/' + args.base.strip('/') + '/' if args.base.strip('/') else '/'
    origin = args.origin.rstrip('/')
    out = Path(args.out)

    if out.resolve() == ROOT.resolve():
        # Never wipe the repository: a root build only replaces its own files.
        print('Building the site into the repository root (Pages serves main -> /).')
        out.mkdir(parents=True, exist_ok=True)
    else:
        if args.clean and out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True, exist_ok=True)

    print(f'Building static site')
    print(f'  origin : {origin}')
    print(f'  base   : {base}')
    print(f'  output : {out}')

    products = read_catalog(Path(args.db))
    print(f'  catalog: {len(products)} published product(s)')

    # ---- static-only overrides (e.g. the admin gate page) ------------------ #
    overrides = 0
    if OVERRIDES.is_dir():
        for source in sorted(OVERRIDES.rglob('*')):
            if not source.is_file():
                continue
            relative = source.relative_to(OVERRIDES)
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            text = source.read_text(encoding='utf-8').replace('{base}', base)
            target.write_text(text, encoding='utf-8')
            overrides += 1

    # ---- copy and rewrite the public tree --------------------------------- #
    copied = 0
    for source in sorted(PUBLIC.rglob('*')):
        if not source.is_file():
            continue
        relative = source.relative_to(PUBLIC)
        if relative.name.startswith('.') and relative.name != '.nojekyll':
            continue
        if relative.as_posix() in STATIC_OMIT or relative.suffix.lower() == '.md':
            continue
        if (out / relative).is_file() and (OVERRIDES / relative).is_file():
            continue  # the override already owns this path
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() in TEXT_SUFFIXES:
            text = source.read_text(encoding='utf-8')
            target.write_text(rewrite_references(text, base), encoding='utf-8')
        else:
            shutil.copy2(source, target)
        copied += 1
    print(f'  copied : {copied} file(s) from public/')
    if overrides:
        print(f'  gated  : {overrides} static override(s) applied (admin console)')

    # ---- static catalog snapshot ------------------------------------------ #
    data_dir = out / 'data'
    data_dir.mkdir(exist_ok=True)
    (data_dir / 'products.json').write_text(
        json.dumps(products, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    generated = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    snapshot_js = (
        '/* Generated by tools/build_static.py — static catalog snapshot. */\n'
        'window.AXIA_STATIC = window.AXIA_STATIC || {};\n'
        f'window.AXIA_STATIC.generatedAt = "{generated}";\n'
        f'window.AXIA_STATIC.products = {json.dumps(products, ensure_ascii=False)};\n'
    )
    (data_dir / 'products.js').write_text(snapshot_js, encoding='utf-8')

    # ---- page shell -------------------------------------------------------- #
    index_path = out / 'index.html'
    html = index_path.read_text(encoding='utf-8')
    html = html.replace('<link rel="canonical" href="/">',
                        f'<link rel="canonical" href="{origin}{base}">')
    html = html.replace('<link rel="canonical" href="' + base + '">',
                        f'<link rel="canonical" href="{origin}{base}">')
    if 'og:url' not in html:
        html = html.replace('<meta property="og:type" content="website">',
                            f'<meta property="og:type" content="website"><meta property="og:url" content="{origin}{base}">')
    # Load the snapshot before the app so the catalog is available offline.
    html = html.replace(
        f'<script src="{base}effects.js',
        f'<script src="{base}data/products.js?v=static-1"></script>\n  <script src="{base}effects.js',
    )
    html = inject_adapter(html, base)
    snapshot_tag = f'<script src="{base}static-config.js?v=static-1" defer></script>\n  '
    html = html.replace('<script src="' + base + 'data/products.js', snapshot_tag + '<script src="' + base + 'data/products.js')
    index_path.write_text(html, encoding='utf-8')

    config_js = (
        '/* Generated by tools/build_static.py — runtime configuration for the static build. */\n'
        'window.AXIA_STATIC = window.AXIA_STATIC || {};\n'
        f'window.AXIA_STATIC.base = {json.dumps(base)};\n'
        f'window.AXIA_STATIC.origin = {json.dumps(origin)};\n'
        f'window.AXIA_STATIC.mode = {json.dumps("demo" if args.demo else "static")};\n'
        f'window.AXIA_STATIC.generatedAt = window.AXIA_STATIC.generatedAt || {json.dumps(generated)};\n'
    )
    (out / 'static-config.js').write_text(config_js, encoding='utf-8')

    # ---- demo backend for the admin console -------------------------------- #
    # The static build has no Python server, so the console is answered in the
    # browser by public/demo-backend.js. It is injected ONLY here, never in the
    # server build, so the real console keeps its server-verified sessions.
    admin_path = out / 'admin' / 'index.html'
    if admin_path.is_file():
        admin_html = admin_path.read_text(encoding='utf-8')
        demo_tag = f'<script src="{base}demo-backend.js?v=static-1" defer></script>'
        if 'demo-backend.js' not in admin_html:
            admin_html = admin_html.replace(
                f'<script src="{base}admin/admin.js',
                demo_tag + '\n  <script src="' + base + 'admin/admin.js')
        admin_path.write_text(admin_html, encoding='utf-8')

    # ---- SEO files --------------------------------------------------------- #
    (out / 'sitemap.xml').write_text(build_sitemap(origin, base), encoding='utf-8')
    (out / 'robots.txt').write_text(build_robots(origin, base), encoding='utf-8')
    (out / '.nojekyll').write_text('', encoding='utf-8')

    print(f'  wrote  : index.html, static-config.js, data/products.json, data/products.js,')
    print(f'           sitemap.xml, robots.txt, .nojekyll')

    # ---- sanity check ------------------------------------------------------ #
    problems = []
    index_text = index_path.read_text(encoding='utf-8')
    for script in re.findall(r'<script src="([^"]+)"', index_text):
        clean = script.split('?')[0]
        if clean.startswith('http'):
            continue
        path = out / clean.lstrip('/').replace(base.lstrip('/'), '', 1)
        if not path.is_file():
            problems.append(f'missing script: {clean}')
    for link in re.findall(r'<link[^>]+href="([^"]+)"', index_text):
        clean = link.split('?')[0]
        if clean.startswith(('http', '#', 'data:')):
            continue
        path = out / clean.lstrip('/').replace(base.lstrip('/'), '', 1)
        if not path.is_file() and not clean.endswith('/'):
            problems.append(f'missing asset: {clean}')
    if problems:
        print('  WARNING:')
        for problem in sorted(set(problems)):
            print(f'    - {problem}')
        return 1

    print('  check  : every referenced local script and stylesheet exists')
    print(f'\nDone. Preview locally with:\n  python3 -m http.server -d {out} 8080')
    print(f'Then open http://localhost:8080{base}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
