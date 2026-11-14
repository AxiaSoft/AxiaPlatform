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

# Only real, crawlable documents are listed. The storefront's inner screens are
# hash routes (#/products), which a crawler never fetches as separate pages, so
# listing them would advertise addresses that are not documents. The storefront
# is one page with server-rendered blog sections alongside it.
SITEMAP_ROUTES = [
    ('', 'weekly', '1.0'),
    ('blog/', 'daily', '0.9'),
]

# The adapter must be registered before app.js, so it is inserted immediately
# before the app bundle's script tag.
def app_script_re(base: str) -> re.Pattern:
    """Match the app bundle tag with or without the base prefix applied yet.

    inject_adapter() runs on the shell before rewrite_references(), so src is
    still '/app.js' at that point. Matching only the prefixed form silently fell
    through to the end-of-body fallback - which put the adapter *after* the app
    bundle, the one order that cannot work.
    """
    return re.compile(
        r'(\s*)<script src="(?:' + re.escape(base) + r'|/)?app\.js[^"]*" defer></script>')


def read_catalog(db_path: Path, base: str = '/') -> list[dict]:
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
            print(f'  database not readable ({exc}); using the committed catalog', file=sys.stderr)
    if not rows:
        # The database is gitignored, so a clean checkout has no catalog. The
        # published build at the repo root is committed, and its snapshot is
        # what the live site currently serves - reuse it rather than shipping an
        # empty catalog. Undo the base prefix the previous build added, so the
        # next build re-applies it once instead of stacking it.
        published = ROOT / 'data' / 'products.json'
        if published.is_file():
            try:
                rows = json.loads(published.read_text(encoding='utf-8')) or []
            except Exception:
                rows = []
            prefix = base.rstrip('/')
            for row in rows:
                cover = row.get('cover')
                if isinstance(cover, str) and prefix and cover.startswith(prefix + '/'):
                    row['cover'] = cover[len(prefix):]
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


def load_articles(out, DB_PATH=None) -> list[dict]:
    """Published articles, for the blog pages and for Xiona's knowledge base.

    The same list feeds both, so the assistant can never cite a post the site
    does not show, or miss one it does.
    """
    import sys
    sys.path.insert(0, str(ROOT / 'server'))
    try:
        import blog as blog_module  # noqa: WPS433 - the build stays standalone
    except Exception:
        blog_module = None

    # data/articles.json is the source of truth for the static build: it is
    # committed, so a checkout with no database still publishes the same
    # articles. A database is only consulted when that file is absent (a local
    # build straight from the console's data).
    articles = []
    source = ROOT / 'data' / 'articles.json'
    if not source.is_file():
        source = out / 'data' / 'articles.json'
    if source.is_file():
        try:
            articles = json.loads(source.read_text(encoding='utf-8')) or []
        except Exception:
            articles = []
    if not articles and blog_module is not None:
        try:
            import sqlite3
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM articles WHERE status='published' "
                                "ORDER BY COALESCE(published_at, created_at) DESC, id DESC").fetchall()
            articles = [blog_module.article_out(r, full=True) for r in rows]
            conn.close()
        except Exception:
            articles = []
    if not articles:
        try:
            fallback = out / 'data' / 'articles.json'
            if fallback.is_file() and fallback != source:
                articles = json.loads(fallback.read_text(encoding='utf-8')) or []
        except Exception:
            articles = []
    return articles


def write_blog(out, base: str, origin: str, DB_PATH=None) -> None:
    """Render /blog/ (and any exported articles) as static HTML."""
    import sys
    sys.path.insert(0, str(ROOT / 'server'))
    try:
        import blog  # noqa: WPS433 - imported here so the build stays standalone
    except Exception:
        print('  blog: skipped (server/blog.py not importable)')
        return

    # data/articles.json is the source of truth for the static build: it is
    # committed, so a checkout with no database still publishes the same
    # articles. A database is only consulted when that file is absent (a local
    # build straight from the console's data).
    articles = []
    source = ROOT / 'data' / 'articles.json'
    if not source.is_file():
        source = out / 'data' / 'articles.json'
    if source.is_file():
        try:
            articles = json.loads(source.read_text(encoding='utf-8')) or []
        except Exception:
            articles = []
    if not articles:
        try:
            import sqlite3
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM articles WHERE status='published' "
                                "ORDER BY COALESCE(published_at, created_at) DESC, id DESC").fetchall()
            articles = [blog.article_out(r, full=True) for r in rows]
            conn.close()
        except Exception:
            articles = []
    if not articles:
        try:
            fallback = out / 'data' / 'articles.json'
            if fallback.is_file() and fallback != source:
                articles = json.loads(fallback.read_text(encoding='utf-8')) or []
        except Exception:
            articles = []

    def rebase(markup: str) -> str:
        """Point root-relative links at the deployment sub-path."""
        if base == '/':
            return markup
        return re.sub(r'(href|src)="/(?!/)', lambda m: f'{m.group(1)}="{base}', markup)

    # Persian is the published language. The English mirror is written from the
    # same articles, using any stored translation (out/data/translations.json)
    # and otherwise labelling the page as untranslated rather than pretending.
    stored = {}
    tsource = out / 'data' / 'translations.json'
    if tsource.is_file():
        try:
            stored = {str(k): v for k, v in (json.loads(tsource.read_text(encoding='utf-8')) or {}).items()}
        except Exception:
            stored = {}

    def english(article, full=False):
        """An article's English fields, or None when no translation is stored."""
        hit = stored.get(str(article.get('slug')))
        if not hit:
            return None
        item = dict(article)
        for field in ('title', 'summary', 'body'):
            item[field] = hit.get(field) or article.get(field) or ''
        item['language'] = 'en'
        item['translated'] = True
        if not full:
            item.pop('body', None)
        return item

    fa_posts = articles
    # Every article gets an English URL, because the language switch and the
    # hreflang alternates both point at one. A post with no stored translation
    # is rendered in its original language and labelled as untranslated.
    en_posts = []
    for article in articles:
        hit = english(article)
        if hit:
            en_posts.append(hit)
        else:
            item = dict(article)
            item['translated'] = False
            en_posts.append(item)

    def write_lang(root_dir, lang, posts, prefix):
        blog_dir = root_dir / 'blog'
        blog_dir.mkdir(parents=True, exist_ok=True)
        index_body = blog.render_index(posts, lang=lang, base=base.rstrip('/'))
        fa_url = f'{origin}{base}blog/'
        en_url = f'{origin}{base}en/blog/'
        index_head = blog.head_tags(
            title='AXIASOFT Blog — notes on engineering and product design' if lang == 'en'
                  else 'وبلاگ AXIASOFT — یادداشت‌های مهندسی و طراحی محصول',
            description='Articles from Axiasoft on building websites, mobile applications, custom software and digital products.' if lang == 'en'
                        else 'مقاله‌های آکسیا سافت درباره طراحی وب‌سایت، اپلیکیشن موبایل، نرم‌افزار سفارشی و ساختن محصول دیجیتال.',
            canonical=en_url if lang == 'en' else fa_url, origin=origin, base=base,
            kind='blog', items=posts, lang=lang,
            alt_url=fa_url if lang == 'en' else en_url)
        # The shell builds its own links from `base`; only the body carries
        # root-relative URLs that need rebasing, so rebase it before wrapping.
        (blog_dir / 'index.html').write_text(
            blog.shell(head=index_head, body=rebase(index_body), lang=lang,
                       base=base.rstrip('/')), encoding='utf-8')

        for article in posts:
            item = dict(article)
            item['html'] = blog.render_markdown(article.get('body') or '')
            item.setdefault('translated', True)
            folder = blog_dir / str(article.get('slug') or '')
            folder.mkdir(parents=True, exist_ok=True)
            body = blog.render_article(item, lang=lang, base=base.rstrip('/'))
            post_fa = f'{origin}{base}blog/{article.get("slug")}/'
            post_en = f'{origin}{base}en/blog/{article.get("slug")}/'
            head = blog.head_tags(
                title=f"{article.get('title', '')} — AXIASOFT",
                description=article.get('summary') or blog.plain_text(article.get('body') or '', 160),
                canonical=post_en if lang == 'en' else post_fa,
                origin=origin, base=base, kind='article', article=item, lang=lang,
                alt_url=post_fa if lang == 'en' else post_en)
            # Rebase inside-out: head/body URLs first, then wrap. Re-running the
            # rebase over a finished document would prefix the shell's already
            # correct links a second time.
            (folder / 'index.html').write_text(
                blog.shell(head=rebase(head), body=rebase(body), lang=lang,
                           base=base.rstrip('/'), slug=str(article.get('slug') or '')),
                encoding='utf-8')
        return blog_dir

    blog_dir = write_lang(out, 'fa', fa_posts, 'blog')
    # The English index lists only posts that really are in English; the
    # per-article pages still exist for every slug so no link dead-ends.
    written = write_lang(out / 'en', 'en', [p for p in en_posts if p.get('translated')], 'en/blog')
    for article in en_posts:
        if article.get('translated'):
            continue
        item = dict(article)
        item['html'] = blog.render_markdown(article.get('body') or '')
        folder = written / str(article.get('slug') or '')
        folder.mkdir(parents=True, exist_ok=True)
        body = blog.render_article(item, lang='en', base=base.rstrip('/'))
        (folder / 'index.html').write_text(
            blog.shell(head='', body=rebase(body), lang='en', base=base.rstrip('/'),
                       slug=str(article.get('slug') or '')), encoding='utf-8')

    (blog_dir / 'feed.xml').write_text(
        blog.render_rss(origin, base, articles), encoding='utf-8')
    print(f'  blog  : {len(articles)} article(s) to /blog/, '
          f'{len(en_posts)} translated to /en/blog/')


def build_sitemap(origin: str, base: str) -> str:
    """The site map, with each page's language mirror named as an alternate."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
             ' xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for route, freq, priority in SITEMAP_ROUTES:
        mirror = f'en/{route}' if route.startswith('blog') else ''
        alternates = ''
        if mirror:
            alternates = (f'<xhtml:link rel="alternate" hreflang="fa-IR" href="{origin}{base}{route}"/>'
                          f'<xhtml:link rel="alternate" hreflang="en" href="{origin}{base}{mirror}"/>')
        lines.append(f'  <url><loc>{origin}{base}{route}</loc>'
                     f'<changefreq>{freq}</changefreq><priority>{priority}</priority>{alternates}</url>')
        if mirror:
            lines.append(f'  <url><loc>{origin}{base}{mirror}</loc>'
                         f'<changefreq>{freq}</changefreq><priority>{priority}</priority>{alternates}</url>')
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


def unclosed_scripts(html: str) -> list[str]:
    """Return <script src> tags that no </script> ever closes.

    An unclosed <script> swallows every tag after it as raw text, so one missing
    </script> in the shell silently kills the next bundle - that is exactly how
    the static adapter once vanished from an otherwise green build.
    """
    tags = list(re.finditer(r'<script\b[^>]*\bsrc="([^"]+)"[^>]*>', html))
    dangling: list[str] = []
    for index, tag in enumerate(tags):
        stop = tags[index + 1].start() if index + 1 < len(tags) else len(html)
        if '</script>' not in html[tag.end():stop]:
            dangling.append(tag.group(1))
    return dangling


XIONA_PAGES = [
    # (function in app.js, route, title, policy key, aliases)
    # The aliases are the words a visitor actually types, in both languages.
    # The page copy is English, so a Persian question needs these to reach it.
    ('services', '#/services', 'Services', None,
     'خدمات سرویس طراحی توسعه وب اپلیکیشن نرم‌افزار services development design'),
    ('about', '#/about', 'About AXIASOFT', None,
     'درباره شرکت تیم ما آکسیا سافت about company team who are you'),
    ('contact', '#/contact', 'Start a project', None,
     'تماس سفارش درخواست پروژه شروع ثبت contact order request project start quote'),
    ('policy', '#/privacy', 'Privacy policy', 'privacy',
     'حریم خصوصی داده اطلاعات privacy data'),
    ('policy', '#/terms', 'Terms and conditions', 'terms',
     'قوانین شرایط استفاده terms conditions'),
    ('policy', '#/refunds-policy', 'Refund and return policy', 'refunds-policy',
     'بازپرداخت لغو استرداد refund cancellation'),
]

# The page copy lives inside template strings in app.js, so the build renders
# those functions in a tiny JS sandbox and stores the text. Xiona then learns the
# same sentences a visitor reads - there is no second copy of the copy.
XIONA_RENDERER = r"""
const fs = require('fs');
const vm = require('vm');
const src = fs.readFileSync(process.argv[2], 'utf8');
const products = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const settings = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
const pages = JSON.parse(process.argv[5]);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
  (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const wanted = [...new Set(pages.map((p) => p[0]))];
let code = '';
for (const fn of wanted) {
  const at = src.indexOf('function ' + fn + '(');
  if (at < 0) continue;
  let end = src.length;
  for (const marker of ['\nfunction ', '\n/*']) {
    const hit = src.indexOf(marker, at + 1);
    if (hit > 0 && hit < end) end = hit;
  }
  code += src.slice(at, end) + '\n';
}
const sandbox = {products, site: settings, esc, AXIA_T: (s) => s,
  document: {documentElement: {lang: 'fa'}}, location: {hash: '#/'}, console};
vm.createContext(sandbox);
vm.runInContext(code + '\nthis.__pages = {' + wanted.map((fn) => fn + ': typeof ' + fn + " === 'function' ? " + fn + ' : null').join(', ') + '};', sandbox);
const out = [];
for (const [fn, route, title, key, aliases] of pages) {
  const callable = sandbox.__pages[fn];
  if (!callable) continue;
  let html;
  try { html = key ? callable(key) : callable(); } catch (e) { continue; }
  // Block-level tags must become a separator, not nothing: replacing them with
  // '' glues a heading to the paragraph after it ('support AURION is...').
  // </p> and friends separate sentences; <br> only separates lines, and inside
  // a headline it splits a phrase ('From first idea / to ready to grow').
  const text = String(html)
    .replace(/<\/(p|h[1-6]|li|div|section|article|td|th|tr)>/gi, '. ')
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<[^>]*>/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/\.\s*\.+/g, '.')
    .replace(/(^|[\.!?]\s*)\.+/g, '$1')
    .trim();
  if (text.length > 80) out.push({topic: key || fn, route, title, text, aliases: aliases || ''});
}
process.stdout.write(JSON.stringify(out));
"""

def xiona_dictionary(source: Path) -> list[list[str]]:
    """The site's own Persian/English dictionary, as word-pair candidates.

    Xiona answers a Persian question against English page copy. The words that
    translate one into the other are not written into the assistant: the UI
    already ships a dictionary (public/i18n.js) so a Persian reader can use the
    same product, and that dictionary is the site's own statement about what
    means what. Handing it over means a string added to the UI tomorrow is
    understood by the assistant after the next build, with no code change here
    and no list to keep in step.

    Only the pairs are extracted; the alignment into a word lexicon happens in
    the engine, once, on both sides (JS and Python).
    """
    if not source.exists():
        return []
    text = source.read_text(encoding='utf-8')
    try:
        start = text.index('const fa={') + len('const fa={')
        end = text.index('\n};', start)
    except ValueError:
        return []
    block = text[start:end]
    pairs, seen = [], set()
    for left, right in re.findall(r"""['"]([^'"]*)['"]\s*:\s*['"]([^'"]*)['"]""", block):
        left = left.strip()
        right = right.strip()
        if not left or not right or left == right:
            continue
        if not re.search(r'[\u0600-\u06FF]', right):
            continue
        key = (left.lower(), right)
        if key in seen:
            continue
        seen.add(key)
        pairs.append([left, right])
    return pairs


def xiona_pages(out, base: str, settings_path: Path) -> list[dict]:
    """Render the SPA's page copy and return it as knowledge chunks.

    The assistant must be able to answer "how does a refund work?" on a static
    build, where no page has been rendered yet. Rather than duplicate the site
    copy in a second file, the build evaluates the same functions the browser
    runs and keeps their text.
    """
    import subprocess
    script = ROOT / 'tools' / '_xiona_pages.js'
    script.write_text(XIONA_RENDERER, encoding='utf-8')
    try:
        result = subprocess.run(
            ['node', str(script), str(PUBLIC / 'app.js'),
             str(out / 'data' / 'products.json'), str(settings_path),
             json.dumps(XIONA_PAGES)],
            capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f'  xiona : page copy skipped ({result.stderr.strip()[:120]})', file=sys.stderr)
            return []
        pages = json.loads(result.stdout or '[]')
    except Exception as exc:
        print(f'  xiona : page copy skipped ({type(exc).__name__})', file=sys.stderr)
        return []
    finally:
        script.unlink(missing_ok=True)
    # Routes are stored root-relative with a hash; the site is a hash router, so
    # they work unchanged under any sub-path.
    print(f'  xiona : {len(pages)} page(s) of site copy indexed')
    return pages


def inject_adapter(html: str, base: str) -> str:
    """Insert the static adapter just before the app bundle."""
    tag = f'<script src="{base}static-adapter.js?v=static-1" defer></script>'
    if 'static-adapter.js' in html:
        return html
    match = app_script_re(base).search(html)
    if match:
        # Insert after the tag's indentation but before the tag itself, so the
        # adapter still runs first: match.start() is the whitespace, not the tag.
        at = match.start(1) + len(match.group(1))
        return html[:at] + tag + html[at:]
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

    products = read_catalog(Path(args.db), base)
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
    # A product can point at a cover that is not in the tree — for example one
    # uploaded on a server whose upload folder is not committed. Say so now:
    # a broken image on the live site is much harder to trace than a build note.
    missing = []
    for product in products:
        cover = str(product.get('cover') or '')
        if cover.startswith('/') and not cover.startswith('//'):
            if not (out / cover.lstrip('/')).is_file():
                missing.append(cover)
    for cover in sorted(set(missing)):
        print(f'  warning: cover not found in the build: {cover}', file=sys.stderr)
    if overrides:
        print(f'  gated  : {overrides} static override(s) applied (admin console)')

    # ---- static catalog snapshot ------------------------------------------ #
    _xiona_articles = load_articles(out, Path(getattr(args, 'db', '') or ''))
    # Covers are stored root-absolute ('/brand/arya-logo.png'). On Pages the app
    # lives under a sub-path, so the browser has to ask for
    # '/AxiaPlatform/brand/...'. Prefixing here keeps the stored data unchanged
    # and means the page never has to second-guess a product image path.
    # Idempotent: the build is run with --out . so the committed root build is
    # the input of the next one. Prefixing twice would bake in
    # '/AxiaPlatform/AxiaPlatform/...' and break every product image.
    prefix = base.rstrip('/')
    for product in products:
        cover = product.get('cover')
        if isinstance(cover, str) and cover.startswith('/') and not cover.startswith('//'):
            if prefix and not cover.startswith(prefix + '/'):
                product['cover'] = prefix + cover
    data_dir = out / 'data'
    data_dir.mkdir(exist_ok=True)
    # ---- storefront settings snapshot ------------------------------------- #
    # The browser build has no API, so the settings the admin console edits are
    # shipped alongside the products. The same document answers GET /api/site in
    # the Python server, so the storefront has one shape to read in both builds.
    # Written first because Xiona renders the page copy with these settings.
    try:
        sys.path.insert(0, str(ROOT / 'server'))
        import site_settings as settings_module
        settings = settings_module.merge({})
    except Exception:
        settings = {}
    (data_dir / 'settings.json').write_text(
        json.dumps(settings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (data_dir / 'products.json').write_text(
        json.dumps(products, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # The page copy is rendered from the same products.json the storefront
    # loads, so it is read after that file exists.
    _xiona_pages = xiona_pages(out, base, data_dir / 'settings.json')
    generated = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    snapshot_js = (
        '/* Generated by tools/build_static.py — static catalog snapshot. */\n'
        'window.AXIA_STATIC = window.AXIA_STATIC || {};\n'
        f'window.AXIA_STATIC.generatedAt = "{generated}";\n'
        f'window.AXIA_STATIC.products = {json.dumps(products, ensure_ascii=False)};\n'
    )
    # Xiona learns from the same snapshot the storefront renders, so an answer
    # can never cite a product or post the visitor cannot open.
    _xiona_pairs = xiona_dictionary(PUBLIC / 'i18n.js')
    snapshot_js += (
        f'window.AXIA_STATIC.articles = '
        f'{json.dumps(_xiona_articles, ensure_ascii=False)};\n'
        f'window.AXIA_STATIC.pages = '
        f'{json.dumps(_xiona_pages, ensure_ascii=False)};\n'
        f'window.AXIA_STATIC.pairs = '
        f'{json.dumps(_xiona_pairs, ensure_ascii=False)};\n'
    )
    (data_dir / 'products.js').write_text(snapshot_js, encoding='utf-8')

    # ---- blog ------------------------------------------------------------- #
    # The published site is static, so there is no article database here. If the
    # source tree carries published articles (data/articles.json, written by the
    # console's export) they are rendered now; otherwise an honest empty index is
    # published, so /blog/ is never a dead link.
    write_blog(out, base, origin, DB_PATH=Path(getattr(args, 'db', '') or ''))

    (data_dir / 'settings.js').write_text(
        '/* Generated by tools/build_static.py — storefront settings snapshot. */\n'
        'window.AXIA_STATIC = window.AXIA_STATIC || {};\n'
        f'window.AXIA_STATIC.settings = {json.dumps(settings, ensure_ascii=False)};\n',
        encoding='utf-8')

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
        f'<script src="{base}data/products.js?v=static-1"></script>\n'
        f'  <script src="{base}data/settings.js?v=static-1"></script>\n  <script src="{base}effects.js',
    )
    html = inject_adapter(html, base)
    snapshot_tag = f'<script src="{base}static-config.js?v=static-1" defer></script>\n  '
    html = html.replace('<script src="' + base + 'data/products.js', snapshot_tag + '<script src="' + base + 'data/products.js')
    # A missing </script> in the shell silently disables every bundle after it.
    # Fail the build instead of shipping a page whose adapter never runs.
    dangling = unclosed_scripts(html)
    if dangling:
        raise SystemExit(
            'index.html has unclosed <script src> tag(s): ' + ', '.join(dangling)
            + ' - an unclosed tag swallows the tags after it as text.')
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
        demo_tag = f'<script src="{base}demo-backend.js?v=static-3" defer></script>'
        if 'demo-backend.js' not in admin_html:
            admin_html = admin_html.replace(
                f'<script src="{base}admin/admin.js',
                demo_tag + '\n  <script src="' + base + 'admin/admin.js')
        # The settings screen reads its starting values before the API answers,
        # so the snapshot has to be present on this page too.
        settings_tag = f'<script src="{base}data/settings.js?v=static-1"></script>'
        if 'data/settings.js' not in admin_html:
            admin_html = admin_html.replace(
                f'<script src="{base}effects.js',
                settings_tag + '\n  <script src="' + base + 'effects.js')
        admin_path.write_text(admin_html, encoding='utf-8')

    # ---- SEO files --------------------------------------------------------- #
    (out / 'sitemap.xml').write_text(build_sitemap(origin, base), encoding='utf-8')
    (out / 'robots.txt').write_text(build_robots(origin, base), encoding='utf-8')
    (out / '.nojekyll').write_text('', encoding='utf-8')

    print(f'  wrote  : index.html, static-config.js, data/products.json, data/products.js,')
    print(f'           data/settings.json, data/settings.js,')
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
