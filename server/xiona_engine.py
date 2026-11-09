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

# 'تر' is deliberately absent: it is the comparative ending ('سریع‌تر') but also
# the last two letters of ordinary nouns, and stripping it turns 'کامپیوتر'
# into 'کامپیو'. A stemmer that mangles the word it was given is worse than one
# that keeps a plural - and the JS engine must agree with this list exactly.
_FA_SUFFIXES = ('هایشان', 'هایمان', 'هایتان', 'هایش', 'هایم', 'هایت', 'های',
                'هایی', 'ها', 'ترین', 'شان', 'مان', 'تان', 'یی', 'یم',
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


# --------------------------------------------------------------------------- #
# Vocabulary
#
# A visitor types Persian; most of what this site publishes is English. The
# bridge is not a list written here: the UI ships a Persian/English dictionary
# so a Persian reader can use the same product, and the build hands those pairs
# over. A string added to the UI tomorrow is understood after the next build.
# --------------------------------------------------------------------------- #

class Lexicon:
    """Word-level translations learned from the site's own dictionary."""

    def __init__(self, pairs=None):
        en_to_fa, fa_to_en, seen = {}, {}, {}
        for pair in pairs or []:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            left, right = str(pair[0] or ''), str(pair[1] or '')
            if not left or not right:
                continue
            english, persian = tokenize(left), tokenize(right)
            if len(english) == 1 and len(persian) == 1:
                if is_persian(english[0]) != is_persian(persian[0]):
                    en_to_fa.setdefault(english[0], {})
                    en_to_fa[english[0]][persian[0]] = \
                        en_to_fa[english[0]].get(persian[0], 0) + 1
                    fa_to_en.setdefault(persian[0], {})
                    fa_to_en[persian[0]][english[0]] = \
                        fa_to_en[persian[0]].get(english[0], 0) + 1
            # A phrase pair does not say which word means which, but it does say
            # the two sides describe one thing. Recorded as co-topic evidence
            # only - never as a translation, because a guessed translation is an
            # invented answer.
            for f in persian:
                if len(f) < 3:
                    continue
                bucket = seen.setdefault(f, {})
                for e in english:
                    if len(e) < 3:
                        continue
                    bucket[e] = bucket.get(e, 0) + 1
        self.en = {k: max(v, key=v.get) for k, v in en_to_fa.items() if v}
        self.fa = {k: max(v, key=v.get) for k, v in fa_to_en.items() if v}
        self.known = {k: [w for w, _ in sorted(v.items(), key=lambda kv: -kv[1])]
                      for k, v in seen.items()}

    def __len__(self):
        return len(self.fa)


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
        # The site's own Persian/English dictionary, handed over by the build.
        self.lexicon = Lexicon()

    def vocabulary(self, pairs):
        """Teach the assistant the site's own vocabulary.

        The UI ships a Persian/English dictionary so a Persian reader can use the
        same product. Those pairs are the site's own statement about what means
        what, so they become search terms - not a list kept in this file.
        """
        if pairs:
            self.lexicon = Lexicon(pairs)
        return self

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
        if source.get('pairs'):
            self.vocabulary(source['pairs'])
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

    # ------------------------------------------------------------- evidence
    def reach(self, term, extra=None):
        """How many chunks a word touches, counting its translation."""
        words = [term] + [w for w in (extra or []) if w != term]
        return sum(1 for doc in self.docs
                   if any(word in doc['tokens'] for word in words))

    def known(self, term):
        """Is this word part of what the site publishes at all?"""
        direct = self.lexicon.fa.get(term) or self.lexicon.en.get(term)
        if self.reach(term, [direct] if direct else []) > 0:
            return True
        partners = self.lexicon.known.get(term) or []
        return bool(partners) and self.reach(partners[0]) > 0

    def expand(self, terms):
        """The words to search for, beyond the visitor's own.

        A one-to-one translation is used as a translation. A phrase partner is
        only used when the corpus cannot contain the word at all, and only the
        strongest two of them - taking the whole phrase turns a question about
        price into a question about orders, scope and delivery as well.
        """
        out = []
        for term in terms:
            direct = self.lexicon.fa.get(term) or self.lexicon.en.get(term)
            candidates = [direct] if direct else []
            if not candidates and self.reach(term) == 0:
                for word in self.lexicon.known.get(term, []):
                    if word in STOPWORDS['en'] or self.reach(word) == 0:
                        continue
                    candidates.append(word)
                    if len(candidates) >= 2:
                        break
            for word in candidates:
                if word and word not in out and word not in terms:
                    out.append(word)
        return out

    def absent_terms(self, terms):
        return [t for t in terms if not self.known(t)]

    def topics(self):
        seen, out = set(), []
        for doc in self.docs:
            if not doc['title'] or doc['topic'] in seen or doc['topic'] == 'article':
                continue
            seen.add(doc['topic'])
            out.append(doc['title'])
        return out

    def carries_question(self, terms, absent):
        """Does a word the site knows actually answer this question?"""
        for term in terms:
            if term in absent:
                continue
            direct = self.lexicon.fa.get(term) or self.lexicon.en.get(term)
            if self.reach(term, [direct] if direct else []) >= 1:
                return True
        return False

    def explained(self, word, terms, absent):
        """Is an unknown word accounted for by another word in the question?"""
        mine = self.lexicon.known.get(word) or []
        for other in terms:
            if other == word or other in absent:
                continue
            theirs = self.lexicon.known.get(other) or []
            if any(shared in theirs for shared in mine):
                return True
        return False

    # --------------------------------------------------------------- search
    def search(self, question, language=None, limit=None):
        terms = tokenize(question)
        if not terms:
            return []
        bridged = self.expand(terms)

        # Which of the visitor's words carry the question? A word spread across
        # most of the corpus describes the setting, not the subject.
        informative = []
        for term in terms:
            direct = self.lexicon.fa.get(term) or self.lexicon.en.get(term)
            reach = self.reach(term, [direct] if direct else [])
            if reach == 0:
                if self.known(term):
                    informative.append(term)
            elif reach < 0.6 * len(self.docs):
                informative.append(term)
        meaningful = max(1, len(informative))

        phrase = re.sub(r'\s+', ' ', fold(question).lower()).strip()
        ranked = []
        for doc in self.docs:
            counts = {}
            for token in doc['tokens']:
                counts[token] = counts.get(token, 0) + 1
            score = 0.0
            matched = own = 0
            covered = []

            def weigh(term, weight):
                nonlocal score
                freq = counts.get(term, 0)
                if not freq:
                    return False
                norm = doc['length'] / (self.avg_length.get(doc['language']) or 1)
                score += weight * self._idf(doc['language'], term) * (
                    (freq * (self.k1 + 1)) / (freq + self.k1 * (1 - self.b + self.b * norm)))
                return True

            for term in terms:
                if weigh(term, 1.0):
                    matched += 1
                    own += 1
                    if term not in covered:
                        covered.append(term)
            for word in bridged:
                if not weigh(word, 0.85):
                    continue
                matched += 1
                for term in terms:
                    direct = self.lexicon.fa.get(term) or self.lexicon.en.get(term)
                    if direct == word or word in (self.lexicon.known.get(term) or []):
                        if term not in covered:
                            covered.append(term)
            if not matched:
                continue
            # A chunk holding a translation but none of the visitor's own words
            # is a fallback, never a better answer than a direct hit.
            if own == 0:
                score *= 0.35

            total = len(terms) + len(bridged)
            score *= 1 + 0.45 * (matched / total)
            if matched == total:
                score *= 1.18
            if len(phrase) > 3 and phrase in doc['text'].lower():
                score *= 1.55
            label = fold(doc['title'] + ' ' + doc['topic'] + ' ' +
                         doc.get('keywords', '')).lower()
            all_terms = terms + bridged
            label_hits = sum(1 for term in all_terms if term in label)
            if label_hits:
                score *= 1 + 1.8 * (label_hits / len(all_terms))

            hits = sum(1 for term in informative if term in covered)
            ranked.append({'doc': doc, 'score': score, 'matched': matched,
                           'ownMatched': own, 'strongMatched': matched,
                           'coverage': min(1.0, hits / meaningful)})
        ranked.sort(key=lambda hit: -hit['score'])
        return ranked[:limit or self.max_results]

    def _judge(self, best):
        """True when the best hit is too weak to answer with.

        Coverage, not raw score: a BM25 score depends on corpus size, so an
        absolute threshold tuned on the live site rejects everything on a small
        one. Coverage counts only the words that carry the question.
        """
        if not best:
            return True
        if best['score'] < self.min_score:
            return True
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
        # A sentence with the rare word the question is about is the better lead
        # than one that merely repeats a common word.
        weight = {}
        for term in terms:
            seen = sum(1 for part in parts if term in tokenize(part))
            weight[term] = 1.0 / seen if seen else 0.0
        scored = []
        for index, part in enumerate(parts):
            tokens = tokenize(part)
            hits = sum(weight.get(term, 0.0) for term in terms if term in tokens)
            scored.append((hits, index))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        keep, used = [], 0
        for _, index in scored:
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
        language = 'fa' if is_persian(question) else 'en'
        labels = _LABELS[language]
        query = str(question or '').strip()[:MAX_QUESTION]
        if not query:
            return {'answer': labels['unsure'], 'source': 'empty',
                    'language': language, 'citations': []}
        if not self.size():
            return {'answer': labels['nodocs'], 'source': 'empty-index',
                    'language': language, 'citations': []}
        if _GREETING.match(query) and len(tokenize(query)) <= 2:
            return {'answer': labels['greeting'], 'source': 'greeting',
                    'language': language, 'citations': []}

        # There used to be two regex tables here that answered price and
        # "are you a bot" with a ready-made sentence. Reciting is not answering,
        # and it got the question wrong: 'پروژه چقدر طول میکشد' (how long does a
        # project take) matched the price table on 'چقدر' and was answered about
        # pricing. What can be settled from the site's own text is whether the
        # word the question hangs on is present in what it publishes.
        terms = tokenize(query)
        # A question with no content words left is a question about the
        # assistant itself: 'شما کی هستید' is pronoun and copula only. The site
        # publishes what this assistant is, so answer from that chunk.
        if not terms:
            # The site's own description of this assistant is the chunk read from
            # the panel; look it up by topic so a stray 'support' match in the
            # privacy page cannot answer a question about identity.
            hits_self = [{'doc': doc, 'score': 1.0} for doc in self.docs
                         if doc['topic'] == 'assistant'] or \
                        self.search('Xiona assistant', 'any', limit=1)
            if hits_self:
                doc = hits_self[0]['doc']
                return {'answer': self._focus(doc['text'], [], 320),
                        'source': 'knowledge', 'language': language,
                        'citations': [{'title': doc['title'], 'route': doc['route'],
                                       'topic': doc['topic'],
                                       'score': round(hits_self[0]['score'], 2)}]}
            return {'answer': labels['unsure'], 'source': 'no-match',
                    'language': language, 'citations': []}

        absent = self.absent_terms(terms)
        subject_missing = any(not self.explained(word, terms, absent) for word in absent)
        if absent and (len(absent) == len(terms) or subject_missing) and \
                not self.carries_question(terms, absent):
            return {'answer': uncovered_text(absent, language, self.topics()),
                    'source': 'uncovered', 'language': language,
                    'citations': [], 'absent': absent}

        hits = self.search(query, 'any')
        if self._judge(hits[0] if hits else None):
            return {'answer': labels['unsure'], 'source': 'no-match',
                    'language': language, 'citations': []}

        used = self.expand(terms)
        for term in terms:
            if term in _all_tokens_of(hits):
                used.append(term)
        parts, citations, seen = [], [], set()
        for hit in hits:
            doc = hit['doc']
            key = (doc['topic'], doc['title'])
            if key in seen:
                continue
            seen.add(key)
            if parts and hit['score'] < hits[0]['score'] * 0.55:
                break
            body = self._focus(doc['text'], used, 340)
            if not body:
                continue
            parts.append(body)
            citations.append({'title': doc['title'], 'route': doc['route'],
                              'topic': doc['topic'], 'score': round(hit['score'], 2)})
            if len(' '.join(parts)) > 700:
                break
        return {'answer': ' '.join(parts), 'source': 'knowledge',
                'language': language, 'citations': citations}


def _all_tokens_of(hits):
    tokens = set()
    for hit in hits:
        tokens.update(hit['doc']['tokens'])
    return tokens


def uncovered_text(absent, language, topics):
    """Say plainly that the site does not cover a subject, and name what it does.

    The list of what the site covers comes from the index, so the sentence stays
    true as the site changes.
    """
    join = '، ' if language == 'fa' else ', '
    subject = join.join(absent)
    listing = join.join(topics[:5])
    if language == 'fa':
        return ('این سایت دربارهٔ «' + subject + '» چیزی منتشر نکرده است، '
                'پس پاسخ تأییدشده‌ای ندارم.' +
                (' آنچه منتشر شده: ' + listing + '.' if listing else '') +
                ' می‌توانید پرسش خود را از صفحهٔ «شروع پروژه» مطرح کنید.')
    return ('This site does not publish anything about "' + subject +
            '", so I have no answer for it.' +
            (' What it does publish: ' + listing + '.' if listing else '') +
            ' You can raise it on the Start a project page.')


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


def build_engine(products, articles, pages=None, pairs=None):
    """Index what the site publishes. Used by the server and by tests.

    ``pages`` is the page copy the build renders and ``pairs`` is the site's own
    Persian/English dictionary. Both are optional, so a caller with only a
    catalog still works - but supplying them is what lets a Persian question
    reach English page copy.
    """
    return Engine().vocabulary(pairs).learn({
        'products': products or [],
        'articles': articles or [],
        'pages': pages or [],
    })


def get_engine(products_provider, articles_provider, stamp,
               pages_provider=None, pairs_provider=None):
    """Return a cached engine, rebuilding only when the content stamp changes.

    ``stamp`` is anything comparable that changes when content does (a row count
    and the newest updated_at, for example). Rebuilding on every question would
    be wasteful; never rebuilding would answer from a stale catalog.
    """
    global _engine, _content_stamp
    if _engine is None or stamp != _content_stamp:
        _engine = build_engine(
            products_provider(), articles_provider(),
            pages_provider() if pages_provider else None,
            pairs_provider() if pairs_provider else None)
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
