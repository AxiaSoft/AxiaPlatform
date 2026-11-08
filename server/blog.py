"""Editorial content: articles written in the console and published to /blog/.

The article body is a small, deliberately limited Markdown dialect. It is
converted here, on the server, so the public pages never execute HTML that an
editor typed. The same conversion runs in the browser for the demo console, in
public/blog.js, so both paths produce identical markup.

Supported: headings (# - ####), paragraphs, **bold**, *italic*, `code`,
[links](https://…), - / 1. lists, > quotes, fenced code blocks, --- rules and
blank-line separated blocks. Everything else is escaped text.
"""
import html
import re

MAX_TITLE = 120
MAX_SLUG = 90
MAX_SUMMARY = 320
MAX_BODY = 60000
MAX_TAG = 32

SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')

# A post is "published" when the editor flips the switch; drafts are only
# visible inside the console.
STATUSES = ('draft', 'published')

INLINE_RULES = (
    (re.compile(r'`([^`\n]+)`'), r'<code>\1</code>'),
    (re.compile(r'\*\*([^*\n]+)\*\*'), r'<strong>\1</strong>'),
    (re.compile(r'(?<!\*)\*([^*\n]+)\*(?!\*)'), r'<em>\1</em>'),
)


def slugify(value):
    """ASCII, dash-separated slug. Non-Latin text becomes an empty string and
    the caller falls back to the article id, which keeps URLs stable."""
    text = (value or '').strip().lower()
    text = re.sub(r'[^\w\s-]', '', text, flags=re.ASCII)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-{2,}', '-', text).strip('-')
    return text[:MAX_SLUG]


def _inline(text):
    """Escape, then apply the inline rules to the escaped text.

    Links are handled first because their URL has to survive escaping. Only
    http(s) and site-relative targets are accepted; anything else keeps its
    brackets as text."""
    def link(match):
        label, href = match.group(1), match.group(2).strip()
        if not re.match(r'^(https?://|#/|/)', href): return match.group(0)
        return f'<a href="{html.escape(href, quote=True)}">{label}</a>'
    # Escape the label but keep the href for the rule below.
    text = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)',
                  lambda m: '\x00LINK' + html.escape(m.group(1)) + '\x00' + m.group(2) + '\x01',
                  text)
    text = html.escape(text, quote=False)
    for pattern, replacement in INLINE_RULES:
        text = pattern.sub(replacement, text)
    def restore(match):
        label, href = match.group(1), match.group(2).strip()
        if not re.match(r'^(https?://|#/|/)', href):
            # An unrecognised scheme is not linkified, and its address is
            # dropped rather than echoed back as text.
            return label
        return f'<a href="{html.escape(href, quote=True)}">{label}</a>'
    return re.sub('\x00LINK(.*?)\x00(.*?)\x01', restore, text)


def render_markdown(source):
    """Turn the article body into sanitised HTML."""
    if not source:
        return ''
    lines = str(source).replace('\r\n', '\n').replace('\r', '\n').split('\n')
    out, buffer, mode = [], [], None

    def flush():
        nonlocal buffer, mode
        if not buffer: mode = None; return
        if mode == 'ul':
            out.append('<ul>' + ''.join(f'<li>{_inline(x)}</li>' for x in buffer) + '</ul>')
        elif mode == 'ol':
            out.append('<ol>' + ''.join(f'<li>{_inline(x)}</li>' for x in buffer) + '</ol>')
        elif mode == 'quote':
            out.append('<blockquote>' + ' '.join(f'<p>{_inline(x)}</p>' for x in buffer) + '</blockquote>')
        elif mode == 'code':
            out.append('<pre><code>' + html.escape('\n'.join(buffer)) + '</code></pre>')
        buffer, mode = [], None

    index = 0
    while index < len(lines):
        raw = lines[index]
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith('```'):
            if mode == 'code':
                flush()
            else:
                flush(); mode = 'code'
            index += 1; continue
        if mode == 'code':
            buffer.append(raw); index += 1; continue

        if not stripped:
            flush(); index += 1; continue

        if re.fullmatch(r'-{3,}|\*{3,}', stripped):
            flush(); out.append('<hr>'); index += 1; continue

        heading = re.match(r'^(#{1,4})\s+(.*)$', stripped)
        if heading:
            flush()
            level = min(len(heading.group(1)) + 1, 5)  # the page owns <h1>
            out.append(f'<h{level}>{_inline(heading.group(2))}</h{level}>')
            index += 1; continue

        bullet = re.match(r'^[-*+]\s+(.*)$', stripped)
        if bullet:
            if mode != 'ul': flush(); mode = 'ul'
            buffer.append(bullet.group(1)); index += 1; continue

        numbered = re.match(r'^\d{1,3}[.)]\s+(.*)$', stripped)
        if numbered:
            if mode != 'ol': flush(); mode = 'ol'
            buffer.append(numbered.group(1)); index += 1; continue

        quoted = re.match(r'^>\s?(.*)$', stripped)
        if quoted:
            if mode != 'quote': flush(); mode = 'quote'
            buffer.append(quoted.group(1)); index += 1; continue

        if mode in ('ul', 'ol'):
            # A wrapped list item continues the previous bullet.
            buffer[-1] += ' ' + stripped; index += 1; continue
        if mode == 'quote':
            buffer[-1] += ' ' + stripped; index += 1; continue

        flush(); out.append(f'<p>{_inline(stripped)}</p>')
        index += 1

    flush()
    return '\n'.join(out)


def plain_text(source, limit=200):
    """A readable excerpt for meta descriptions and card summaries."""
    text = re.sub(r'```.*?```', ' ', source or '', flags=re.S)
    text = re.sub(r'[#>*_`\-]+', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit]


def reading_minutes(source):
    words = len(re.findall(r'\w+', plain_text(source, 100000)))
    return max(1, round(words / 200))


def clean_article(payload, article_id=None):
    """Validate one submitted article. Returns (values, errors)."""
    errors = {}
    title = str(payload.get('title') or '').strip()[:MAX_TITLE]
    if len(title) < 4:
        errors['title'] = 'Give the article a title of at least 4 characters.'

    slug = slugify(payload.get('slug') or title)
    if not slug:
        slug = f'article-{article_id}' if article_id else ''
    if not slug:
        errors['slug'] = 'Use Latin letters and dashes, or leave it to be generated.'
    elif len(slug) > MAX_SLUG:
        errors['slug'] = 'Too long.'

    summary = str(payload.get('summary') or '').strip()[:MAX_SUMMARY]
    body = str(payload.get('body') or '')[:MAX_BODY]
    if len(plain_text(body)) < 40:
        errors['body'] = 'Write at least a short paragraph.'

    tags = payload.get('tags') or []
    if isinstance(tags, str):
        tags = [t for t in re.split(r'[,\n]', tags)]
    tags = [str(t).strip()[:MAX_TAG] for t in tags if str(t).strip()][:6]

    status = payload.get('status') if payload.get('status') in STATUSES else 'draft'
    cover = str(payload.get('cover') or '').strip()[:300]
    return {
        'title': title,
        'slug': slug,
        'summary': summary,
        'body': body,
        'cover': cover,
        'tags': tags,
        'status': status,
        'language': 'fa' if str(payload.get('language')) == 'fa' else 'en',
    }, errors


def article_out(row, full=False):
    """Shape one row for the API. Bodies are omitted from list responses."""
    tags = row['tags'] if 'tags' in row.keys() else '[]'
    try:
        import json
        tags = json.loads(tags or '[]')
    except Exception:
        tags = []
    item = {
        'id': row['id'],
        'slug': row['slug'],
        'title': row['title'],
        'summary': row['summary'] or plain_text(row['body'], MAX_SUMMARY),
        'cover': row['cover'] or '',
        'tags': tags,
        'status': row['status'],
        'language': row['language'],
        'reading_minutes': reading_minutes(row['body']),
        'published_at': row['published_at'] or row['created_at'],
        'updated_at': row['updated_at'],
    }
    if full:
        item['body'] = row['body']
        item['html'] = render_markdown(row['body'])
    return item


# ---------------------------------------------------------------------------
# Server-rendered pages
# ---------------------------------------------------------------------------
# The storefront is a client-side app. Articles are not: a crawler has to see
# the words, the title and the structured data in the first response. These
# templates produce complete documents, styled by the same stylesheet.

def esc(value):
    return html.escape(str(value if value is not None else ''), quote=True)


# Persian is the language the site is written in; the English mirror is the
# same pages with the interface strings swapped. Article bodies are authored
# once and translated on demand (see docs/agent.md for wiring a model), so an
# untranslated body is shown in the language it was written rather than
# pretending a translation exists.
COPY = {
    'fa': {
        'nav_products': 'محصولات', 'nav_services': 'خدمات', 'nav_blog': 'وبلاگ',
        'nav_about': 'درباره ما', 'nav_cta': 'شروع پروژه', 'skip': 'پرش به محتوا',
        'blog_title': 'وبلاگ AXIASOFT', 'blog_h1a': 'یادداشت‌هایی دربارهٔ ساختن',
        'blog_h1b': 'محصول دیجیتال',
        'blog_lede': 'از طراحی و مهندسی تا جزئیاتی که یک وب‌سایت یا اپلیکیشن را قابل‌اعتماد می‌کند.',
        'empty': 'هنوز مقاله‌ای منتشر نشده است. نخستین یادداشت‌ها به‌زودی از پنل مدیریت منتشر می‌شوند.',
        'min_read': 'دقیقه مطالعه', 'back': 'بازگشت به همهٔ مقاله‌ها',
        'source_note': 'این مقاله هنوز ترجمه نشده و به زبان اصلی منتشر شده است.',
        'all_posts': 'همهٔ مقاله‌ها', 'contact': 'تماس', 'privacy': 'حریم خصوصی',
        'tagline': 'نرم‌افزار سنجیده برای آنچه پیش می‌آید.',
        'made': 'مهندسی‌شده با هدفمندی', 'feed': 'وبلاگ', 'home': 'خانهٔ AXIASOFT',
        'published': 'منتشرشده در', 'more': 'خواندن مقاله',
    },
    'en': {
        'nav_products': 'Products', 'nav_services': 'Services', 'nav_blog': 'Blog',
        'nav_about': 'About', 'nav_cta': 'Start a project', 'skip': 'Skip to content',
        'blog_title': 'AXIASOFT Blog', 'blog_h1a': 'Notes on building',
        'blog_h1b': 'digital products',
        'blog_lede': 'From design and engineering to the details that make a website or application trustworthy.',
        'empty': 'No articles have been published yet. The first notes will be published from the admin panel.',
        'min_read': 'min read', 'back': 'Back to all articles',
        'source_note': 'This article has not been translated yet and is shown in its original language.',
        'all_posts': 'All articles', 'contact': 'Contact', 'privacy': 'Privacy',
        'tagline': 'Considered software for what comes next.',
        'made': 'Engineered with intent', 'feed': 'Blog', 'home': 'AXIASOFT home',
        'published': 'Published', 'more': 'Read the article',
    },
}


def copy_for(lang):
    """Interface strings for a language code, defaulting to Persian."""
    return COPY['en' if str(lang).lower().startswith('en') else 'fa']


def localised(row, db, target='en'):
    """Return an article row's fields in `target`, translating once and caching.

    The translation is stored against a hash of the source text, so editing a
    post in the console invalidates its English copy automatically. If no
    provider is configured (or the call fails) the original text is returned
    along with ``translated: False`` — the caller labels the page instead of
    passing off the source as a translation.
    """
    import agent  # local import: blog stays importable without the agent
    import hashlib
    data = dict(row)
    if target == 'en' and str(data.get('language') or 'fa') == 'fa':
        source = '\n\x00\n'.join([data.get('title') or '', data.get('summary') or '',
                                   data.get('body') or ''])
        digest = hashlib.sha256(source.encode('utf-8')).hexdigest()[:32]
        cached = db.execute(
            'SELECT * FROM article_translations WHERE article_id=? AND lang=? AND source_hash=?',
            (data['id'], target, digest)).fetchone()
        if cached:
            data.update(title=cached['title'], summary=cached['summary'], body=cached['body'],
                        translated=True, translated_lang=target)
            return data
        if not agent.translation_available():
            data.update(translated=False)
            return data
        parts, failed = {}, False
        for field in ('title', 'summary', 'body'):
            source_text = data.get(field) or ''
            if not source_text.strip():
                parts[field] = ''
                continue
            out, error = agent.translate(source_text, target='English')
            if out is None:
                failed = True
                break
            parts[field] = out
        if failed:
            data.update(translated=False)
            return data
        db.execute(
            'INSERT INTO article_translations(article_id, lang, title, summary, body, source_hash) '
            'VALUES(?,?,?,?,?,?) ON CONFLICT(article_id, lang) DO UPDATE SET '
            'title=excluded.title, summary=excluded.summary, body=excluded.body, '
            'source_hash=excluded.source_hash',
            (data['id'], target, parts['title'], parts['summary'], parts['body'], digest))
        data.update(parts, translated=True, translated_lang=target)
        return data
    data.update(translated=True)
    return data


def article_page(row, db, lang='fa'):
    """An article shaped for one language, with its rendered HTML."""
    lang = pick_lang(lang)
    alt = lang if str(row['language'] or 'fa') != lang else str(row['language'] or 'fa')
    data = localised(row, db, target=alt)
    html_body = render_markdown(data.get('body') or '')
    data['html'] = html_body
    data['reading_minutes'] = reading_minutes(data.get('body') or '')
    return data


def pick_lang(value):
    """Normalise a requested language to 'en' or 'fa'."""
    return 'en' if str(value or '').lower().startswith('en') else 'fa'


def head_tags(title, description, canonical, origin, base, kind, article=None, items=None, lang='fa', alt_url=None):
    """Open Graph, Twitter, canonical, hreflang and JSON-LD for one page."""
    lang = pick_lang(lang)
    t = copy_for(lang)
    # alt_url is this same page in the other language. Whichever language we
    # are rendering, canonical is that language's URL and alt_url the mirror;
    # falling back to canonical keeps the pair resolvable either way.
    if lang == 'en':
        en_url, fa_url = canonical, (alt_url or canonical)
    else:
        fa_url, en_url = canonical, (alt_url or canonical)
    image = f'{origin}{base}/brand/axiasoft-wordmark.png'
    if article and article.get('cover'):
        cover = str(article['cover'])
        image = cover if cover.startswith('http') else f'{origin}{base}/{cover.lstrip("/")}'

    blocks = [
        f'<title>{esc(title)}</title>',
        f'<meta name="description" content="{esc(description)}">',
        f'<link rel="canonical" href="{esc(canonical)}">',
        # Both language versions are announced so a crawler indexes them as one
        # document with two translations instead of duplicate content.
        f'<link rel="alternate" hreflang="fa-IR" href="{esc(fa_url)}">',
        f'<link rel="alternate" hreflang="en" href="{esc(en_url)}">',
        f'<link rel="alternate" hreflang="x-default" href="{esc(fa_url)}">',
        '<meta name="robots" content="index, follow, max-image-preview:large">',
        f'<meta property="og:type" content="{"article" if kind == "article" else "website"}">',
        f'<meta property="og:site_name" content="AXIASOFT">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        f'<meta property="og:url" content="{esc(canonical)}">',
        f'<meta property="og:image" content="{esc(image)}">',
        f'<meta property="og:locale" content="{"en_US" if lang == "en" else "fa_IR"}">',
        f'<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{esc(title)}">',
        f'<meta name="twitter:description" content="{esc(description)}">',
        f'<meta name="twitter:image" content="{esc(image)}">',
    ]

    import json as _json
    if kind == 'article' and article:
        blocks.append('<script type="application/ld+json">' + _json.dumps({
            '@context': 'https://schema.org',
            '@type': 'BlogPosting',
            'headline': article['title'],
            'description': description,
            'inLanguage': 'en' if lang == 'en' else 'fa-IR',
            'url': canonical,
            'mainEntityOfPage': {'@type': 'WebPage', '@id': canonical},
            'datePublished': article.get('published_at'),
            'dateModified': article.get('updated_at') or article.get('published_at'),
            'keywords': ', '.join(article.get('tags') or []),
            'wordCount': len(re.findall(r'\w+', article.get('body') or '')),
            'author': {'@type': 'Organization', 'name': 'AXIASOFT', 'url': origin},
            'publisher': {'@type': 'Organization', 'name': 'AXIASOFT',
                          'logo': {'@type': 'ImageObject', 'url': image}},
            'image': image,
        }, ensure_ascii=False) + '</script>')
    if kind == 'blog':
        blocks.append('<script type="application/ld+json">' + _json.dumps({
            '@context': 'https://schema.org',
            '@type': 'Blog',
            'name': 'وبلاگ AXIASOFT',
            'inLanguage': 'fa-IR',
            'url': canonical,
            'publisher': {'@type': 'Organization', 'name': 'AXIASOFT'},
            'blogPost': [{
                '@type': 'BlogPosting',
                'headline': a['title'],
                'url': f'{origin}{base}/blog/{a["slug"]}/',
                'datePublished': a.get('published_at'),
                'description': a.get('summary') or '',
            } for a in (items or [])[:20]],
        }, ensure_ascii=False) + '</script>')
        blocks.append(f'<link rel="alternate" type="application/rss+xml" title="AXIASOFT · وبلاگ" href="{esc(origin + base)}/blog/feed.xml">')
    return '\n  '.join(blocks)


def shell(head, body, lang='fa', base='', slug=''):
    """Complete document around a rendered blog page.

    `lang` switches the whole chrome — direction, navigation, footer — so the
    English mirror is a real page and not a translated body inside a Persian
    frame.
    """
    lang = pick_lang(lang)
    t = copy_for(lang)
    direction = 'rtl' if lang == 'fa' else 'ltr'
    root = base.rstrip('/')
    blog_home = f'{root}/blog/'
    # The language switch points at the same page in the other language.
    if lang == 'en':
        other_lang, switch_label = 'fa', 'فارسی'
    else:
        other_lang, switch_label = 'en', 'English'
    tail = f'{slug}/' if slug else ''
    other_lang_url = (f'{root}/blog/{tail}' if lang == 'en' else f'{root}/en/blog/{tail}')
    return f'''<!doctype html>
<html lang="{lang}" dir="{direction}" data-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark light">
  <meta name="theme-color" content="#080d18">
  {head}
  <link rel="preload" href="{root}/fonts/Vazirmatn-Variable.woff2" as="font" type="font/woff2" crossorigin>
  <link rel="stylesheet" href="{root}/styles.css?v=site-4">
  <link rel="stylesheet" href="{root}/blog.css?v=3">
</head>
<body class="blog-body">
<div class="ambient ambient-one"></div><div class="ambient ambient-two"></div>
<a class="skip-link" href="#main">{t['skip']}</a>
<header class="topbar">
  <a href="{root}/" class="brand" aria-label="AXIASOFT home"><span class="brand-mark"><img src="{root}/brand/axiasoft-original.png" alt="AXIASOFT"></span><img class="brand-wordmark" src="{root}/brand/axiasoft-wordmark.png" alt="AXIASOFT"></a>
  <nav class="nav-links" aria-label="{t['nav_products']}"><a href="{root}/#/products">{t['nav_products']}</a><a href="{root}/#/services">{t['nav_services']}</a><a href="{blog_home}" aria-current="page">{t['nav_blog']}</a><a href="{root}/#/about">{t['nav_about']}</a></nav>
  <div class="nav-actions"><a class="blog-lang" href="{other_lang_url}" hreflang="{other_lang}" lang="{other_lang}" rel="alternate">{switch_label}</a><a class="button button-small button-primary" href="{root}/#/contact">{t['nav_cta']} <span>↗</span></a></div>
</header>
<main class="blog-main" id="main">{body}</main>
<footer class="footer">
  <div class="footer-top"><a class="brand" href="{root}/"><span class="brand-mark"><img src="{root}/brand/axiasoft-original.png" alt="AXIASOFT"></span><img class="brand-wordmark" src="{root}/brand/axiasoft-wordmark.png" alt="AXIASOFT"></a>
  <p>{t['tagline']}</p>
  <div class="footer-links"><a href="{root}/#/contact">{t['contact']}</a><a href="{blog_home}">{t['feed']}</a><a href="{root}/#/privacy">{t['privacy']}</a></div></div>
  <div class="footer-bottom"><span>© AXIASOFT</span><span>{t['made']} <span class="blue">✦</span></span></div>
</footer>
</body></html>'''


def _date(value):
    if not value: return ''
    return str(value)[:10].replace('-', '/')


def render_index(items, site=None, lang='fa', base=''):
    """The blog landing page."""
    lang = pick_lang(lang)
    t = copy_for(lang)
    root = base.rstrip('/')
    cards = []
    for a in items:
        tags = ''.join(f'<span class="blog-tag">{esc(t)}</span>' for t in (a.get('tags') or [])[:3])
        cards.append(f'''<article class="blog-card">
  <a class="blog-card-link" href="{root}/blog/{esc(a['slug'])}/">
    <div class="blog-card-meta"><time datetime="{esc(_date(a.get('published_at')))}">{esc(_date(a.get('published_at')))}</time><span>{esc(a.get('reading_minutes') or 1)} {t['min_read']}</span></div>
    <h2>{esc(a['title'])}</h2>
    <p>{esc(a.get('summary') or '')}</p>
    {f'<div class="blog-tags">{tags}</div>' if tags else ''}
  </a>
</article>''')
    empty = f'<div class="blog-empty"><p>{t["empty"]}</p></div>'
    return f'''<div class="container">
<section class="blog-hero">
  <div class="eyebrow">{t['blog_title']}</div>
  <h1>{t['blog_h1a']} <span class="gradient">{t['blog_h1b']}</span></h1>
  <p>{t['blog_lede']}</p>
</section>
<section class="blog-grid">{''.join(cards) or empty}</section>
</div>'''


def render_article(article, site=None, lang='fa', base=''):
    """One article page with a breadcrumb and related links."""
    lang = pick_lang(lang)
    t = copy_for(lang)
    root = base.rstrip('/')
    tags = ''.join(f'<span class="blog-tag">{esc(x)}</span>' for x in (article.get('tags') or []))
    cover = ''
    if article.get('cover'):
        cover = f'<img class="blog-cover" src="{esc(article["cover"])}" alt="{esc(article["title"])}">'
    # An article written in the other language keeps its own direction so the
    # prose is readable even before a translation exists, and the page says so
    # rather than presenting the source as a translation.
    body_dir = 'rtl' if str(article.get('language') or 'fa') == 'fa' else 'ltr'
    notice = ''
    if article.get('translated') is False:
        notice = f'<p class="blog-notice" lang="{article.get("language") or "fa"}">{t["source_note"]}</p>'
    return f'''<div class="container">
<nav class="blog-crumbs" aria-label="{t['home']}"><a href="{root}/">{t['nav_products']}</a><span>/</span><a href="{root}/blog/">{t['feed']}</a><span>/</span><span>{esc(article['title'])}</span></nav>
<article class="blog-article">
  <header class="blog-article-head">
    <div class="blog-card-meta"><time datetime="{esc(_date(article.get('published_at')))}">{esc(_date(article.get('published_at')))}</time><span>{esc(article.get('reading_minutes') or 1)} {t['min_read']}</span></div>
    <h1>{esc(article['title'])}</h1>
    <p class="blog-lede">{esc(article.get('summary') or '')}</p>
    {f'<div class="blog-tags">{tags}</div>' if tags else ''}
  </header>
  {cover}
  {notice}
  <div class="blog-prose" dir="{body_dir}">{article.get('html') or ''}</div>
</article>
<p class="blog-back"><a href="{root}/blog/">← {t['back']}</a></p>
</div>'''


def render_rss(origin, base, items, title='وبلاگ AXIASOFT'):
    """A small RSS 2.0 feed, which search engines and readers both accept."""
    def cdata(text):
        return '<![CDATA[' + str(text).replace(']]>', ']]&gt;') + ']]>'
    entries = []
    for a in items:
        link = f'{origin}{base}/blog/{a["slug"]}/'
        entries.append(f'''<item>
  <title>{cdata(a['title'])}</title>
  <link>{esc(link)}</link>
  <guid isPermaLink="true">{esc(link)}</guid>
  <description>{cdata(a.get('summary') or '')}</description>
  <pubDate>{esc(a.get('published_at') or '')}</pubDate>
</item>''')
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{cdata(title)}</title>
  <link>{esc(origin + base)}/blog/</link>
  <description>{cdata('یادداشت‌های مهندسی و طراحی محصول AXIASOFT')}</description>
  <language>fa-IR</language>
  <atom:link href="{esc(origin + base)}/blog/feed.xml" rel="self" type="application/rss+xml"/>
  {''.join(entries)}
</channel>
</rss>'''


def render_sitemap(origin, base, items):
    """sitemap.xml listing the site and every published article.

    Each page carries its language mirror as an xhtml:link alternate, which is
    how a crawler is told the Persian and English URLs are one document.
    """
    pairs = [('', '1.0', 'weekly', ''), ('blog/', '0.9', 'daily', 'en/blog/')]
    for a in items:
        pairs.append((f'blog/{a["slug"]}/', '0.8', 'monthly', f'en/blog/{a["slug"]}/'))
    entries = []
    for u, p, c, mirror in pairs:
        alternates = ''
        if mirror:
            alternates = (f'<xhtml:link rel="alternate" hreflang="fa-IR" href="{esc(origin + base)}/{esc(u)}"/>'
                          f'<xhtml:link rel="alternate" hreflang="en" href="{esc(origin + base)}/{esc(mirror)}"/>')
        entries.append(f'<url><loc>{esc(origin + base)}/{esc(u)}</loc>'
                       f'<changefreq>{c}</changefreq><priority>{p}</priority>{alternates}</url>')
        if mirror:
            entries.append(f'<url><loc>{esc(origin + base)}/{esc(mirror)}</loc>'
                           f'<changefreq>{c}</changefreq><priority>{p}</priority>{alternates}</url>')
    body = ''.join(entries)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
            ' xmlns:xhtml="http://www.w3.org/1999/xhtml">' + body + '</urlset>')
