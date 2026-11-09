"""Xiona — the site's own assistant, running on the server.

This is the Python twin of ``public/xiona.js``. Both are self-contained: no API
keys, no outbound requests, no model downloads. They read what the site
publishes, build a searchable knowledge base in memory, and answer from it.

The point of having both is that the same answer is available wherever the site
runs:

* The static build (GitHub Pages) has no server, so the browser engine answers.
* The server build answers through ``/api/agent``, which also lets a configured
  OpenAI-compatible model phrase the answer — never invent it.

If the two implementations ever disagree, they disagree about *scoring*, not
about *facts*: both learn from ``data/articles.json`` and the products table, and
neither can assert anything the site does not publish.

Nothing here reads account data, orders, refunds or payments.
"""
import json
import re

MAX_QUESTION = 800
MAX_HISTORY = 8

# --------------------------------------------------------------------------- #
# Text normalisation — the same rules as the JavaScript engine
# --------------------------------------------------------------------------- #

_FOLD = {
    'ي': 'ی', 'ى': 'ی', 'ئ': 'ی', 'ك': 'ک', 'ﻙ': 'ک', 'ﻚ': 'ک',
    'ة': 'ه', 'ۀ': 'ه', 'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا',
    'ؤ': 'و', '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
    '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
    '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
}

STOPWORDS = {
    'fa': {'و', 'در', 'به', 'از', 'که', 'این', 'را', 'با', 'است', 'برای', 'آن',
           'یک', 'خود', 'تا', 'کرد', 'بر', 'هم', 'نیز', 'یا', 'شد', 'شده', 'های',
           'ها', 'می', 'شود', 'بود', 'اما', 'اگر', 'چه', 'کی', 'چطور', 'چگونه',
           'کجا', 'چقدر', 'آیا', 'دارید', 'دارم', 'دارد', 'کنم', 'کنید',
           'شما', 'ما', 'من', 'او', 'آنها', 'همه', 'بیشتر', 'خیلی', 'چیست', 'چیه',
           'چرا', 'آیا', 'باید', 'توانم', 'توانید', 'می‌توانم', 'می‌توانید', 'هست',
           'هستند', 'هستم', 'نیست', 'بوده', 'دارند', 'لطفا', 'لطفاً', 'بگو',
           'بگویید', 'بگید', 'میخوام', 'می‌خواهم', 'خواستم'},
    'en': {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'do', 'does', 'did',
           'how', 'what', 'when', 'where', 'who', 'why', 'can', 'could', 'would',
           'should', 'i', 'you', 'we', 'they', 'it', 'of', 'to', 'in', 'on', 'for',
           'with', 'and', 'or', 'but', 'my', 'your', 'our', 'me', 'us', 'them',
           'this', 'that', 'these', 'those', 'be', 'been', 'have', 'has', 'had',
           'there', 'about', 'tell', 'please', 'want', 'need', 'get', 'got'},
}

# The site publishes its page copy in English and much of its catalog copy in
# Persian. This bridge maps the words a visitor uses to the words the site uses.
# It is a lexicon, not a translator: it never produces prose, only search terms.
BRIDGE = {
    'محصول': ['product', 'products', 'catalog'],
    'محصولات': ['product', 'products', 'catalog'],
    'کاتالوگ': ['catalog', 'products'],
    'سفارش': ['order', 'request', 'project'],
    'درخواست': ['request', 'order'],
    'پروژه': ['project', 'work'],
    'شروع': ['start', 'begin', 'request'],
    'قیمت': ['price', 'cost', 'quote'],
    'هزینه': ['cost', 'price', 'quote'],
    'زمان': ['time', 'timing', 'delivery'],
    'تحویل': ['delivery', 'deliver'],
    'بازپرداخت': ['refund', 'cancellation'],
    'لغو': ['cancel', 'cancellation'],
    'خدمات': ['services', 'service'],
    'پشتیبانی': ['support', 'help'],
    'حریم': ['privacy', 'data'],
    'خصوصی': ['privacy'],
    'قوانین': ['terms', 'conditions'],
    'شرایط': ['terms', 'conditions'],
    'درباره': ['about', 'company'],
    'شرکت': ['company', 'about'],
    'تیم': ['team', 'about'],
    'تماس': ['contact', 'email'],
    'ارتباط': ['contact'],
    'وب‌سایت': ['website', 'web', 'site'],
    'وبسایت': ['website', 'web', 'site'],
    'سایت': ['website', 'site'],
    'اپلیکیشن': ['application', 'app', 'mobile'],
    'نرم‌افزار': ['software'],
    'طراحی': ['design', 'development'],
    'توسعه': ['development', 'develop'],
    'مقاله': ['article', 'blog', 'post'],
    'مقالات': ['articles', 'blog'],
    'بلاگ': ['blog', 'article'],
    'وبلاگ': ['blog', 'article'],
    'سرعت': ['speed', 'fast', 'performance'],
    'امنیت': ['security', 'secure'],
    'پرداخت': ['payment', 'pay'],
    'حساب': ['account'],
    'کاربر': ['user', 'account'],
    'شخص': ['person', 'human'],
    'انسان': ['human', 'person'],
    'product': ['محصول'], 'products': ['محصولات'], 'order': ['سفارش'],
    'request': ['درخواست'], 'project': ['پروژه'], 'price': ['قیمت'],
    'cost': ['هزینه'], 'refund': ['بازپرداخت'], 'services': ['خدمات'],
    'support': ['پشتیبانی'], 'privacy': ['حریم'], 'terms': ['قوانین'],
    'about': ['درباره'], 'contact': ['تماس'], 'website': ['وب‌سایت'],
    'article': ['مقاله'], 'blog': ['وبلاگ'], 'speed': ['سرعت'],
    'security': ['امنیت'], 'payment': ['پرداخت'], 'account': ['حساب'],
}

# Words that describe the setting rather than the subject: 'قوانین سایت' is a
# question about the terms, not about websites.
VAGUE = {'website', 'web', 'site', 'page', 'section', 'company', 'about',
         'product', 'products', 'service', 'services'}

GENERIC = {
    'fa': {'محصول', 'محصولات', 'کاتالوگ', 'خدمات'},
    'en': {'product', 'products', 'service', 'services', 'catalog'},
}

_FA_SUFFIXES = ('هایشان', 'هایمان', 'هایتان', 'هایش', 'هایم', 'هایت', 'های',
                'هایی', 'ها', 'تر', 'ترین', 'شان', 'مان', 'تان', 'یی', 'یم',
                'ید', 'ند', 'هاست', 'ای', 'ی')

_PERSIAN_RE = re.compile(r'[\u0600-\u06FF]')
_TOKEN_RE = re.compile(r'[a-z0-9]+|[\u0600-\u06FF]+')


def is_persian(text):
    return bool(_PERSIAN_RE.search(str(text or '')))


def fold(text):
    out = ''.join(_FOLD.get(ch, ch) for ch in str(text or ''))
    # Arabic question mark, comma and semicolon sit inside the Arabic block, so
    # a naive token regex keeps them glued to the word ('چیست؟'). Spaces first.
    return re.sub(r'[\u064B-\u0652\u0670\u0640\u200c\u200f\u200e\u061F\u060C\u061B]', ' ', out)


def _strip_suffix(word):
    if not is_persian(word) or len(word) <= 3:
        return word
    for suffix in _FA_SUFFIXES:
        if len(word) - len(suffix) >= 3 and word.endswith(suffix):
            return word[:-len(suffix)]
    return word


def _light_stem(word):
    if not is_persian(word):
        word = re.sub(r'ies$', 'y', word)
        word = re.sub(r'(ses|xes|ches|shes)$', 's', word)
        return re.sub(r'(ing|ed|es|s)$', '', word)
    return _strip_suffix(word)


PHRASES = [
    (re.compile(r'(سفارش|درخواست).*(ثبت|بدم|بدهم|کنم)|چطور.*(سفارش|درخواست)'),
     ['place an order', 'start a project', 'request', 'order']),
    (re.compile(r'بازپرداخت|پس دادن پول|استرداد'), ['refund', 'cancellation']),
    (re.compile(r'حریم خصوصی|اطلاعات من'), ['privacy', 'data protection']),
    (re.compile(r'قوانین|شرایط استفاده'), ['terms', 'conditions']),
    (re.compile(r'با انسان|پشتیبان انسانی|آدم واقعی'), ['human', 'support', 'person']),
    (re.compile(r'قیمت|هزینه|چقدر'), ['price', 'cost', 'quote']),
    (re.compile(r'محصولات|چه چیزی می‌فروشید'), ['products', 'catalog']),
]

# A site with no prices on it cannot answer a price question.
UNCOVERED = [
    (re.compile(r'قیمت|هزینه|چقدر|تعرفه|price|cost|pricing|how much', re.I), {
        'fa': 'قیمت‌ها روی این سایت منتشر نشده‌اند. دامنه و هزینه پس از بررسی درخواست شما '
              'توافق می‌شود؛ می‌توانید از صفحهٔ تماس درخواست بفرستید.',
        'en': 'Prices are not published on this site. Scope and cost are agreed after your '
              'request is reviewed — the Start a project page is the way in.',
    }),
    (re.compile(r'ربات|هوش مصنوعی هستی|are you (an? )?(ai|bot|robot)|who made you', re.I), {
        'fa': 'من Xiona هستم، دستیار همین سایت. کاملاً داخل مرورگر شما اجرا می‌شوم؛ از محتوای '
              'منتشرشدهٔ AXIASOFT یاد می‌گیرم و به هیچ سرویس بیرونی وصل نیستم.',
        'en': "I'm Xiona, this site's assistant. I run entirely in your browser, learn from what "
              "AXIASOFT publishes, and am not connected to any outside service.",
    }),
]


def expand(terms, language, question):
    """Add the question's words in the other language, and its task phrases."""
    out = list(terms)
    extra = []
    folded = fold(question).lower()
    for pattern, words in PHRASES:
        if not pattern.search(folded):
            continue
        for word in words:
            if word not in out and word not in extra:
                extra.append(word)
    for term in terms:
        for word in BRIDGE.get(term, []):
            if word not in out and word not in extra:
                extra.append(word)
    return out, extra


def tokenize(text):
    folded = fold(text).lower()
    language = 'fa' if is_persian(text) else 'en'
    stops = STOPWORDS[language]
    out = []
    for word in _TOKEN_RE.findall(folded):
        if word in stops:
            continue
        stem = _light_stem(word)
        if len(stem) >= 2:
            out.append(stem)
    return out


# --------------------------------------------------------------------------- #
# Sentence and chunk shaping
# --------------------------------------------------------------------------- #

MAX_CHUNK = 420


def clean(text):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', str(text or ''))).strip()


def sentences(text):
    flat = re.sub(r'\s+', ' ', re.sub(r'[#>*`_]', ' ',
                                       re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', str(text or '')))).strip()
    if not flat:
        return []
    parts = re.split(r'(?<=[.!?؟؛])\s+', flat)
    out = []
    for piece in parts:
        piece = piece.strip()
        if not piece:
            continue
        if len(piece) > MAX_CHUNK:
            bits = re.split(r'[,،]\s+', piece)
            buffer = ''
            for bit in bits:
                if len((buffer + ' ' + bit).strip()) > MAX_CHUNK and buffer:
                    out.append(buffer.strip())
                    buffer = bit
                else:
                    buffer = (buffer + ' ' + bit).strip()
            if buffer:
                out.append(buffer.strip())
        else:
            out.append(piece)
    return out


def chunkify(text, min_length=40):
    chunks, buffer = [], ''
    for piece in sentences(text):
        nxt = (buffer + ' ' + piece).strip()
        if len(nxt) > MAX_CHUNK and buffer:
            chunks.append(buffer)
            buffer = piece
        else:
            buffer = nxt
    if buffer:
        chunks.append(buffer)
    merged = []
    for index, chunk in enumerate(chunks):
        if len(chunk) < min_length and merged:
            merged[-1] += ' ' + chunk
        elif len(chunk) >= min_length or index == len(chunks) - 1:
            merged.append(chunk)
        elif merged:
            merged[-1] += ' ' + chunk
        else:
            merged.append(chunk)
    return merged


def tidy(text):
    out = re.sub(r'[↗←→✓⌘▣✕×]', ' ', str(text or ''))
    out = re.sub(r'\s+', ' ', out)
    out = re.sub(r'\.{2,}', '.', out)
    out = re.sub(r'\.\s*,', ',', out)
    out = re.sub(r'^[\s.,;:]+', '', out)
    out = re.sub(r'\.\s*\.', '.', out)
    # A one-word label followed by a full stop is a heading, not a sentence.
    out = re.sub(r'\b([A-Z][a-z]{2,12})\.\s+(?=[A-Z])', r'\1: ', out)
    out = re.sub(r'\s+([.,;:!?؟])', r'\1', out)
    return out.strip()


# --------------------------------------------------------------------------- #
# The engine
# --------------------------------------------------------------------------- #

class Engine:
    """A BM25 index over the site's own content.

    Kept deliberately small and dependency-free: no numpy, no model, no cache
    outside this object. It is built once per process and rebuilt when content
    changes.
    """

    def __init__(self, k1=1.4, b=0.72, max_results=3, min_score=0.05):
        self.k1 = k1
        self.b = b
        self.max_results = max_results
        self.min_score = min_score
        self.docs = []
        self.corpus = {'fa': [], 'en': []}
        self.df = {'fa': {}, 'en': {}}
        self.avg_length = {'fa': 1.0, 'en': 1.0}

    # ---------------------------------------------------------------- build
    def add(self, doc):
        text = clean(doc.get('text'))
        if not text:
            return self
        language = doc.get('language') or ('fa' if is_persian(text) else 'en')
        title = clean(doc.get('title'))
        entry = {
            'id': str(doc.get('id') or f'doc-{len(self.docs)}'),
            'title': title,
            'topic': str(doc.get('topic') or 'general'),
            'route': str(doc.get('route') or ''),
            'language': language,
            'text': text,
            # Keywords are searchable only: matched, never quoted back.
            'keywords': clean(doc.get('keywords')),
            'tokens': tokenize(title + ' ' + title + ' ' + text + ' ' + clean(doc.get('keywords'))),
        }
        entry['length'] = len(entry['tokens']) or 1
        self.docs.append(entry)
        self.corpus[language].append(entry)
        for token in set(entry['tokens']):
            self.df[language][token] = self.df[language].get(token, 0) + 1
        return self

    def learn(self, source):
        """Index everything the site publishes. No list to keep in sync."""
        source = source or {}
        index = 0

        def push(topic, title, route, text, language=None, keywords=''):
            nonlocal index
            for offset, piece in enumerate(chunkify(text)):
                self.add({'id': f'{topic}-{index}', 'title': title, 'topic': topic,
                          'route': route, 'text': piece, 'language': language,
                          'keywords': keywords if offset == 0 else ''})
                index += 1

        for product in source.get('products') or []:
            if not product:
                continue
            if product.get('published') in (0, False):
                continue
            bits = [product.get('summary'), product.get('description')]
            features = product.get('features')
            if isinstance(features, list) and features:
                bits.append(' · '.join(str(f) for f in features))
            technologies = product.get('technologies')
            if isinstance(technologies, list) and technologies:
                bits.append('Technologies: ' + ', '.join(str(t) for t in technologies))
            for key, label in (('status', 'Status'), ('price_label', 'Price'), ('category', 'Category')):
                if product.get(key):
                    bits.append(f'{label}: {product[key]}')
            push('product', product.get('title') or product.get('slug') or 'Product',
                 '#/products/' + str(product.get('slug') or ''),
                 '. '.join(str(bit) for bit in bits if bit))

        for article in source.get('articles') or []:
            if not article:
                continue
            body = article.get('body') or article.get('content') or ''
            text = '. '.join(str(x) for x in (article.get('summary'), body) if x)
            tags = article.get('tags')
            if isinstance(tags, list) and tags:
                text += '. ' + ', '.join(str(t) for t in tags)
            language = 'en' if article.get('language') == 'en' else (
                'fa' if is_persian(str(body) + str(article.get('title'))) else 'en')
            push('article', article.get('title') or article.get('slug') or 'Article',
                 '/blog/' + str(article.get('slug') or '') + '/', text, language,
                 'مقاله مقالات بلاگ وبلاگ نوشته article articles blog post writing')

        for page in source.get('pages') or []:
            if not page:
                continue
            push(page.get('topic') or 'page', page.get('title') or '', page.get('route') or '',
                 page.get('text') or '', page.get('language'), page.get('aliases') or '')

        for language in ('fa', 'en'):
            pool = self.corpus[language]
            total = sum(doc['length'] for doc in pool)
            self.avg_length[language] = (total / len(pool)) if pool else 1.0
        return self

    # ---------------------------------------------------------------- search
    def size(self):
        return len(self.docs)

    def stats(self):
        topics = {}
        for doc in self.docs:
            topics[doc['topic']] = topics.get(doc['topic'], 0) + 1
        return {'chunks': len(self.docs), 'fa': len(self.corpus['fa']),
                'en': len(self.corpus['en']), 'topics': topics}

    def _idf(self, language, token):
        total = len(self.corpus[language]) or 1
        docs = self.df[language].get(token, 0)
        import math
        return math.log(1 + (total - docs + 0.5) / (docs + 0.5))

    def search(self, question, language=None, limit=None):
        base = tokenize(question)
        if not base:
            return []
        language = language or ('fa' if is_persian(question) else 'en')
        pool = self.docs if language == 'any' else (self.corpus.get(language) or [])
        if not pool:
            pool = self.docs

        terms, bridged = expand(base, language, question)
        generic = GENERIC.get(language, set())
        vague_own = sum(1 for t in terms if t in VAGUE or t in generic)
        meaningful = max(1, len(terms) - vague_own)
        phrase = re.sub(r'\s+', ' ', fold(question).lower()).strip()

        ranked = []
        for doc in pool:
            counts = {}
            for token in doc['tokens']:
                counts[token] = counts.get(token, 0) + 1

            def add(term, weight):
                freq = counts.get(term, 0)
                if not freq:
                    return False
                norm = doc['length'] / (self.avg_length.get(doc['language']) or 1)
                nonlocal score
                score += weight * self._idf(doc['language'], term) * (
                    (freq * (self.k1 + 1)) / (freq + self.k1 * (1 - self.b + self.b * norm)))
                return True

            score = 0.0
            matched = own = strong = 0
            for term in terms:
                if add(term, 1.0):
                    matched += 1
                    own += 1
                    if term not in generic:
                        strong += 1
            for term in bridged:
                weight = 0.45 if term in VAGUE else 0.85
                if add(term, weight):
                    matched += 1
                    if term not in generic and term not in VAGUE:
                        strong += 1
            if not matched:
                continue

            total = len(terms) + len(bridged)
            score *= 1 + 0.45 * (matched / total)
            if matched == total:
                score *= 1.18
            if len(phrase) > 3 and phrase in doc['text'].lower():
                score *= 1.55
            # The page's own label is the strongest signal of its subject.
            label = fold(doc['title'] + ' ' + doc['topic'] + ' ' +
                         doc.get('keywords', '')).lower()
            all_terms = terms + bridged
            label_hits = sum(1 for term in all_terms if term in label)
            if label_hits:
                score *= 1 + 1.8 * (label_hits / len(all_terms))

            ranked.append({'doc': doc, 'score': score, 'matched': matched,
                           'ownMatched': own, 'strongMatched': strong,
                           'coverage': min(1.0, strong / meaningful)})
        ranked.sort(key=lambda hit: -hit['score'])
        return ranked[:limit or self.max_results]

    def _judge(self, best):
        """True when the best hit is too weak to answer with.

        Coverage, not raw score: a BM25 score depends on corpus size, so an
        absolute threshold that works on the live site rejects everything on a
        small one. Language is deliberately not part of the test - the page copy
        is English and much of the catalog is Persian, so a Persian question will
        often only match English text.
        """
        if not best:
            return True
        if best['score'] < self.min_score:
            return True
        # coverage already ignores the words that describe the setting rather
        # than the subject, so it is the honest measure of "did I answer".
        return best['coverage'] < 0.5

    # -------------------------------------------------------------- answer
    def _focus(self, text, terms, budget):
        parts = [part for part in sentences(text)
                 if not (len(part) < 48 and len(part.split()) <= 6
                         and not re.search(r'[.؟?!]$', part))]
        if not parts:
            return tidy(text)
        if len(parts) == 1:
            return tidy(parts[0])
        scored = []
        for index, part in enumerate(parts):
            tokens = tokenize(part)
            hits = sum(1 for term in terms if term in tokens)
            scored.append((hits, index))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        keep, used = [], 0
        for hits, index in scored:
            part = parts[index]
            if used + len(part) > budget and keep:
                break
            keep.append(index)
            used += len(part)
            if used > budget * 0.62:
                break
        lead = keep[0] if keep else 0
        keep.sort()
        keep.sort(key=lambda index: (index != lead, index))
        return tidy(' '.join(parts[index] for index in keep))

    def answer(self, question):
        labels = _LABELS['fa' if is_persian(question) else 'en']
        language = 'fa' if is_persian(question) else 'en'
        query = str(question or '').strip()[:MAX_QUESTION]
        if not query:
            return {'answer': labels['unsure'], 'source': 'empty', 'language': language, 'citations': []}
        if not self.size():
            return {'answer': labels['nodocs'], 'source': 'empty-index', 'language': language, 'citations': []}
        if _GREETING.match(query) and len(tokenize(query)) <= 2:
            return {'answer': labels['greeting'], 'source': 'greeting', 'language': language, 'citations': []}
        for pattern, texts in UNCOVERED:
            if pattern.search(query):
                return {'answer': texts[language], 'source': 'policy',
                        'language': language, 'citations': []}

        # Search the whole index, always: the page copy is English and much of
        # the catalog is Persian, so the question's language is a weak signal.
        hits = self.search(query, 'any')
        if self._judge(hits[0] if hits else None):
            return {'answer': labels['unsure'], 'source': 'no-match',
                    'language': language, 'citations': []}

        terms = tokenize(query)
        parts, citations, seen = [], [], set()
        for hit in hits:
            doc = hit['doc']
            key = (doc['topic'], doc['title'])
            if key in seen:
                continue
            seen.add(key)
            if parts and hit['score'] < hits[0]['score'] * 0.55:
                break
            body = self._focus(doc['text'], terms, 340)
            if not body:
                continue
            parts.append(body)
            citations.append({'title': doc['title'], 'route': doc['route'],
                              'topic': doc['topic'], 'score': round(hit['score'], 2)})
            if len(' '.join(parts)) > 700:
                break
        return {'answer': ' '.join(parts), 'source': 'knowledge',
                'language': language, 'citations': citations}


_GREETING = re.compile(r'^(hi|hello|hey|salam|سلام|درود|وقت بخیر|چطوری|خوبی)(\s|$|[!,.؟?])',
                       re.IGNORECASE)

_LABELS = {
    'fa': {
        'unsure': 'پاسخ تأییدشده‌ای برای این سؤال پیدا نکردم. Xiona فقط از محتوای همین سایت '
                  'پاسخ می‌دهد؛ می‌توانم دربارهٔ محصولات، خدمات، فرایند سفارش، AURION، '
                  'مقالات یا قوانین بازپرداخت کمک کنم.',
        'nodocs': 'هنوز دانشی برای پاسخ دادن ندارم. وقتی محصول یا مقاله‌ای منتشر شود، Xiona آن '
                  'را می‌خواند و پاسخ می‌دهد.',
        'greeting': 'سلام. من Xiona هستم؛ دستیار همین سایت. از محتوای منتشرشدهٔ AXIASOFT یاد '
                    'می‌گیرم و مستقیم پاسخ می‌دهم — دربارهٔ محصولات، خدمات، فرایند سفارش، '
                    'AURION، مقالات یا سیاست‌ها بپرسید.',
    },
    'en': {
        'unsure': "I couldn't find an approved answer to that. Xiona answers only from what this "
                  "site publishes — try asking about products, services, the order process, "
                  "AURION, articles, or the refund policy.",
        'nodocs': 'I have no knowledge yet. Once a product or article is published, Xiona reads '
                  'it and can answer from it.',
        'greeting': "Hi, I'm Xiona — this site's own assistant. I learn from what AXIASOFT "
                    "publishes and answer directly. Ask me about products, services, the order "
                    "process, AURION, articles, or the policies.",
    },
}


# --------------------------------------------------------------------------- #
# Process-wide instance, rebuilt when the content behind it changes
# --------------------------------------------------------------------------- #

_engine = None
_content_stamp = None


def build_engine(products, articles):
    """Index a catalog and an article list. Used by the server and by tests."""
    return Engine().learn({'products': products or [], 'articles': articles or []})


def get_engine(products_provider, articles_provider, stamp):
    """Return a cached engine, rebuilding only when the content stamp changes.

    ``stamp`` is anything comparable that changes when content does (a row count
    and the newest updated_at, for example). Rebuilding on every question would
    be wasteful; never rebuilding would answer from a stale catalog.
    """
    global _engine, _content_stamp
    if _engine is None or stamp != _content_stamp:
        _engine = build_engine(products_provider(), articles_provider())
        _content_stamp = stamp
    return _engine


def status(engine=None):
    return {
        'provider': 'local',
        'configured': False,
        'engine': 'on-site',
        'chunks': engine.size() if engine else 0,
        'topics': engine.stats()['topics'] if engine else {},
    }
