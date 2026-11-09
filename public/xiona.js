/*
  Xiona — the site's own assistant.

  Xiona is self-contained: no API keys, no outbound requests, no model
  downloads. It reads the site it lives on — products, articles, services,
  policies, settings — turns that into a searchable knowledge base in the
  browser, and answers from it.

  How it answers:
    1. The question is normalised for Persian and English (Arabic yeh/kaf
       variants, ZWNJ, diacritics, digits, light stemming).
    2. Every knowledge chunk is scored with BM25 over the question's terms. An
       exact-phrase bonus and a title bonus break ties, because a question that
       says "AURION" should reach the AURION page, not the generic services copy.
    3. The best chunks, plus a short window of conversation, are composed into
       an answer. When nothing scores, Xiona says so instead of inventing.

  The same file is the reference for server/agent.py, which implements the same
  scoring in Python for the server build. Keep the two in step.

  Nothing here reads account data, orders, or payments.
*/
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.Xiona = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  /* ------------------------------------------------------------- language */

  // Arabic characters that Persian writers type interchangeably. Folding them
  // means 'كاربر' and 'کاربر' reach the same chunk.
  var FOLD = {
    'ي': 'ی', 'ى': 'ی', 'ئ': 'ی', 'ك': 'ک', 'ﻙ': 'ک', 'ﻚ': 'ک',
    'ة': 'ه', 'ۀ': 'ه', 'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا',
    'ؤ': 'و', '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
    '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
    '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9'
  };

  /* Function words. These carry no subject, so they are dropped before scoring -
     otherwise 'چرا سرعت مهم است' is a question about the word 'است'.
     They are the grammar of the language, not knowledge about the site. */
  var STOPWORDS = {
    fa: ['و', 'در', 'به', 'از', 'که', 'این', 'را', 'با', 'است', 'برای', 'آن',
      'یک', 'خود', 'تا', 'کرد', 'بر', 'هم', 'نیز', 'یا', 'شد', 'شده', 'های',
      'ها', 'می', 'شود', 'بود', 'اما', 'اگر', 'چه', 'کی', 'چطور', 'چگونه',
      'کجا', 'چقدر', 'آیا', 'دارید', 'دارم', 'دارد', 'کنم', 'کنید', 'کنم',
      'شما', 'ما', 'من', 'او', 'آنها', 'همه', 'بیشتر', 'خیلی', 'چیست', 'چیه',
      'چرا', 'آیا', 'باید', 'توانم', 'توانید', 'می‌توانم', 'می‌توانید', 'هست',
      'هستند', 'هستم', 'نیست', 'بوده', 'دارند', 'لطفا', 'لطفاً', 'بگو',
      'بگویید', 'بگید', 'میخوام', 'می‌خواهم', 'خواستم', 'دهید', 'دهد',
      'کن', 'شد', 'کرده', 'دار', 'است؟', 'انجام', 'طور', 'مورد', 'پس',
      // copula and question fragments, as they arrive after stemming
      'هست', 'نیست', 'بودن', 'باش', 'باشه', 'شده', 'کردن', 'دادن', 'گفتن',
      'لازم', 'لطف', 'عزیز', 'بله', 'نه'],
    en: ['the', 'a', 'an', 'is', 'are', 'was', 'were', 'do', 'does', 'did',
      'how', 'what', 'when', 'where', 'who', 'why', 'can', 'could', 'would',
      'should', 'i', 'you', 'we', 'they', 'it', 'of', 'to', 'in', 'on', 'for',
      'with', 'and', 'or', 'but', 'my', 'your', 'our', 'me', 'us', 'them',
      'this', 'that', 'these', 'those', 'be', 'been', 'have', 'has', 'had',
      'there', 'about', 'tell', 'please', 'want', 'need', 'get', 'got']
  };

  // Persian suffixes that carry little meaning on their own. Stripping them is
  // the difference between 'محصولات' and 'محصول' matching, and them not matching.
  /* Suffixes, longest first. 'تر' is deliberately absent: it is the comparative
     ending ('سریع‌تر') but also the last two letters of ordinary nouns, and
     stripping it turns 'کامپیوتر' into 'کامپیو'. A stemmer that mangles the
     word it was given is worse than one that keeps a plural. */
  var FA_SUFFIXES = ['هایشان', 'هایمان', 'هایتان', 'هایش', 'هایم', 'هایت',
    'های', 'هایی', 'ها', 'ترین', 'شان', 'مان', 'تان', 'یی', 'یم', 'ید',
    'ند', 'هاست', 'ای', 'ی'];

  function isPersian(text) {
    return /[\u0600-\u06FF]/.test(String(text || ''));
  }

  function fold(text) {
    var out = '';
    var input = String(text || '');
    for (var i = 0; i < input.length; i++) {
      var ch = input.charAt(i);
      out += FOLD[ch] || ch;
    }
    // ZWNJ joins the halves of a Persian compound ('وب‌سایت') and the reader
    // sees one word, but the Python twin splits on it, and a tokenizer that
    // disagrees makes the two engines answer differently. It becomes a space on
    // both sides, so 'وب‌سایت' is 'وب' + 'سایت' either way.
    return out.replace(/\u200c/g, ' ').replace(/\u200f|\u200e/g, '');
  }

  function stripSuffix(word) {
    for (var i = 0; i < FA_SUFFIXES.length; i++) {
      var suffix = FA_SUFFIXES[i];
      if (word.length > suffix.length + 2 && word.slice(-suffix.length) === suffix) {
        return word.slice(0, -suffix.length);
      }
    }
    return word;
  }

  function lightStem(word) {
    if (!isPersian(word)) {
      if (word.length > 4 && /ies$/.test(word)) return word.slice(0, -3) + 'y';
      if (word.length > 4 && /es$/.test(word)) return word.slice(0, -2);
      if (word.length > 3 && /s$/.test(word) && !/ss$/.test(word)) return word.slice(0, -1);
      return word;
    }
    return stripSuffix(word);
  }

  function tokenize(text) {
    var folded = fold(text).toLowerCase();
    var raw = folded.match(/[a-z0-9]+|[\u0600-\u06FF]+/g) || [];
    var language = isPersian(text) ? 'fa' : 'en';
    var stops = STOPWORDS[language];
    var out = [];
    for (var i = 0; i < raw.length; i++) {
      var word = raw[i];
      if (stops.indexOf(word) !== -1) continue;
      var stem = lightStem(word);
      // The suffix stripper can turn a content-free word into one that is on the
      // list ('هستید' -> 'هست'), so the stem is tested too.
      if (stem !== word && stops.indexOf(stem) !== -1) continue;
      if (stem.length < 2) continue;
      out.push(stem);
    }
    return out;
  }

  /* --------------------------------------------------------------- lexicon

     A visitor types Persian; most of what this site publishes is English. The
     bridge between them is NOT a list written by hand here - a hand-kept list
     only knows the words its author thought of, which is exactly the assistant
     problem: it answers what it was told to answer.

     Instead the site teaches its own vocabulary. The UI ships a Persian/English
     dictionary (public/i18n.js) so a Persian reader can use the same product;
     the build hands those pairs to Xiona, and they are aligned into a word
     lexicon here. If a new UI string is added with a translation, the
     assistant understands it after the next build - no code change.

     Only unambiguous pairs are used: one English word against one Persian
     word. A phrase pair ('Request a quote' / 'درخواست برآورد') does not say
     which word maps to which, so guessing would invent a translation - and an
     invented translation is an invented answer. */

  function buildLexicon(pairs) {
    var enToFa = {};
    var faToEn = {};
    function bump(map, key, value) {
      if (!key || !value || key === value) return;
      if (map[key] === undefined) map[key] = {};
      map[key][value] = (map[key][value] || 0) + 1;
    }
    function surface(text) {
      return fold(text).toLowerCase().replace(/[^a-z0-9\u0600-\u06FF]+/g, ' ').trim();
    }
    for (var i = 0; i < (pairs || []).length; i++) {
      var pair = pairs[i] || [];
      var left = String(pair[0] || '');
      var right = String(pair[1] || '');
      if (!left || !right) continue;
      var english = tokenize(left);
      var persian = tokenize(right);
      // One word each side, and the sides must actually be different languages.
      if (english.length !== 1 || persian.length !== 1) continue;
      if (isPersian(english[0]) === isPersian(persian[0])) continue;
      bump(enToFa, english[0], persian[0]);
      bump(faToEn, persian[0], english[0]);
      // The question is tokenized the same way, but a visitor may type the
      // surface form ('پشتیبانی') where the dictionary stores the stem
      // ('پشتیبان'), or the other way round. Both keys point at one entry.
      var enSurface = surface(left);
      var faSurface = surface(right);
      if (enSurface && enSurface.indexOf(' ') === -1) {
        bump(enToFa, enSurface, persian[0]);
        bump(faToEn, persian[0], enSurface);
      }
      if (faSurface && faSurface.indexOf(' ') === -1) {
        bump(faToEn, faSurface, english[0]);
        bump(enToFa, english[0], faSurface);
      }
    }
    /* A phrase pair does not say which word translates to which - but it does
       say the two sides are about the same thing. That is enough to know a
       Persian word is part of the site's subject matter, which is what the
       coverage test needs, without inventing a word-for-word translation. */
    var seen = {};
    for (var p = 0; p < (pairs || []).length; p++) {
      var row = pairs[p] || [];
      var en = tokenize(row[0] || '');
      var fa = tokenize(row[1] || '');
      if (!en.length || !fa.length) continue;
      for (var f = 0; f < fa.length; f++) {
        if (!seen[fa[f]]) seen[fa[f]] = {};
        for (var q = 0; q < en.length; q++) {
          if (!en[q] || en[q].length < 3) continue;
          seen[fa[f]][en[q]] = (seen[fa[f]][en[q]] || 0) + 1;
        }
      }
    }
    // Rank partners by how many of the site's strings contain them: the word
    // that keeps company with 'قیمت' across several strings is the better
    // search term than one that appeared beside it once.
    var known = {};
    for (var key in seen) {
      if (!Object.prototype.hasOwnProperty.call(seen, key)) continue;
      known[key] = Object.keys(seen[key]).sort(function (a, b) {
        return seen[key][b] - seen[key][a];
      });
    }

    // Keep the strongest partner for each word: the dictionary repeats some
    // concepts, and the most frequent translation is the one the site means.
    function strongest(map) {
      var out = {};
      for (var key in map) {
        if (!Object.prototype.hasOwnProperty.call(map, key)) continue;
        var best = null;
        var bestCount = 0;
        for (var value in map[key]) {
          if (!Object.prototype.hasOwnProperty.call(map[key], value)) continue;
          if (map[key][value] > bestCount) {
            best = value;
            bestCount = map[key][value];
          }
        }
        if (best) out[key] = best;
      }
      return out;
    }
    return { en: strongest(enToFa), fa: strongest(faToEn), known: known, size: 0 };
  }

  /* Expand a question's terms into the other language, using the site's own
     dictionary. Returns the original terms first (the caller weights those
     higher) and the translated ones after. */
  /* Is this word one the site uses as a label - a page or product title, or a
     section topic - rather than only inside a sentence? A site names the things
     it publishes; incidental words live in prose. */
  Engine.prototype.labelled = function (word) {
    for (var i = 0; i < this.docs.length; i++) {
      var label = fold(this.docs[i].title + ' ' + this.docs[i].topic).toLowerCase();
      if (label.indexOf(word) !== -1) return true;
    }
    return false;
  };

  /* How common a word is across the corpus, needed to rank fallback partners
     before they are used as search terms. */
  Engine.prototype.rarity = function (word) {
    var total = this.docs.length || 1;
    var hits = 0;
    for (var i = 0; i < this.docs.length; i++) {
      if (this.docs[i].tokens.indexOf(word) !== -1) hits++;
    }
    return 1 - hits / total;
  };

  function expandWith(lexicon, terms, rarityOf, labelOf) {
    var out = [];
    function push(word) {
      if (word && out.indexOf(word) === -1 && terms.indexOf(word) === -1) out.push(word);
    }
    for (var i = 0; i < terms.length; i++) {
      var term = terms[i];
      var candidates = [term];
      // 'servic' (from 'services') and 'service' are the same word to a reader;
      // try the singular too so a stem on either side still lines up.
      if (/[a-z]s$/.test(term) === false && /[a-z]{4,}$/.test(term)) candidates.push(term + 's');
      if (/[a-z]{5,}s$/.test(term) === false && /[a-z]{4,}e$/.test(term)) candidates.push(term.slice(0, -1));
      for (var c = 0; c < candidates.length; c++) {
        push((lexicon.fa && lexicon.fa[candidates[c]]) ||
             (lexicon.en && lexicon.en[candidates[c]]));
      }
      /* No one-to-one translation: fall back to the words the site's own
         dictionary associates with this one. They are weaker evidence - a
         phrase may mention several things - so they are only search terms, and
         the caller weights them below a real translation. */
      if (!(lexicon.fa && lexicon.fa[term]) && (!rarityOf || rarityOf(term) >= 1)) {
        /* Only when the word itself is missing from the corpus. The partners
           are already ordered by how many of the site's own
           strings pair them with this word - the site's own testimony about
           what belongs together. Take the leading few that the corpus actually
           contains, skipping function words, and let BM25 decide from there.
           Rarity is deliberately not used: it favours a word that happens to
           appear once off-topic ('indicative' in a paragraph about trading)
           over the word the site repeats when it means this thing. */
        /* One good partner, not the whole phrase. A phrase pair lists every
           content word on both sides, so taking several turns a question about
           price into a question about orders, scope and delivery as well - and
           those everyday words then outrank 'price' in the sentences that
           matter. The site's first partner is its strongest statement of what
           this word is about; two is the most that stays precise. */
        var partners = (lexicon.known && lexicon.known[term]) || [];
        var used = 0;
        for (var k = 0; k < partners.length && used < 2; k++) {
          var word = partners[k];
          if (rarityOf && rarityOf(word) >= 1) continue;
          if (STOPWORDS.en.indexOf(word) !== -1) continue;
          push(word);
          used++;
        }
      }
    }
    return out;
  }

  /* ------------------------------------------------------------- knowledge */

  var MAX_CHUNK = 420;

  // Page labels that appear at the top of every policy page and carry no
  // information in an answer. Removing them here keeps them out of every chunk.
  var PAGE_LABELS = /^(AXIASOFT\s*\/\s*INFORMATION|AXIASOFT ACCOUNT|A little about us|Our process|Our values|Our approach)\s*/i;

  function clean(text) {
    var out = String(text || '')
      .replace(/<[^>]*>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    return out.replace(PAGE_LABELS, '');
  }

  // Markdown bodies carry headings and lists; flatten them to sentences so a
  // chunk boundary can land on something a reader recognises.
  function sentences(text) {
    var flat = String(text || '')
      .replace(/[#>*`_]/g, ' ')
      .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
      .replace(/\s+/g, ' ')
      .trim();
    if (!flat) return [];
    var parts = flat.split(/(?<=[.!?؟؛])\s+/);
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      var piece = parts[i].trim();
      if (!piece) continue;
      // A single sentence longer than a chunk is split on commas.
      if (piece.length > MAX_CHUNK) {
        var bits = piece.split(/[,،]\s+/);
        var buffer = '';
        for (var j = 0; j < bits.length; j++) {
          if ((buffer + ' ' + bits[j]).trim().length > MAX_CHUNK && buffer) {
            out.push(buffer.trim());
            buffer = bits[j];
          } else {
            buffer = (buffer + ' ' + bits[j]).trim();
          }
        }
        if (buffer) out.push(buffer.trim());
      } else {
        out.push(piece);
      }
    }
    return out;
  }

  function chunkify(text, minLength) {
    var list = sentences(text);
    var chunks = [];
    var buffer = '';
    for (var i = 0; i < list.length; i++) {
      var next = (buffer + ' ' + list[i]).trim();
      if (next.length > MAX_CHUNK && buffer) {
        chunks.push(buffer);
        buffer = list[i];
      } else {
        buffer = next;
      }
    }
    if (buffer) chunks.push(buffer);
    // Fold trailing scraps into the chunk before them rather than shipping a
    // fragment like "Yes." as its own answer.
    var merged = [];
    for (var k = 0; k < chunks.length; k++) {
      var chunk = chunks[k];
      if (chunk.length < (minLength || 40) && merged.length) {
        merged[merged.length - 1] += ' ' + chunk;
      } else if (chunk.length >= (minLength || 40) || k === chunks.length - 1) {
        merged.push(chunk);
      } else if (merged.length) {
        merged[merged.length - 1] += ' ' + chunk;
      } else {
        merged.push(chunk);
      }
    }
    return merged;
  }

  /* --------------------------------------------------------------- engine */

  function Engine(options) {
    this.docs = [];
    this.corpus = { fa: [], en: [] };
    this.df = { fa: {}, en: {} };
    this.avgLength = { fa: 1, en: 1 };
    var opts = options || {};
    this.k1 = opts.k1 || 1.4;
    this.b = opts.b || 0.72;
    this.maxResults = opts.maxResults || 3;
    // A noise floor only: the real gate is coverage, in _judge().
    this.minScore = opts.minScore || 0.05;
    // The site's own Persian/English dictionary, paired by the build.
    this.lexicon = buildLexicon([]);
    this.vocabulary(pairsOf(opts.pairs));
  }

  function pairsOf(value) {
    return Array.isArray(value) ? value : [];
  }

  /* Teach the assistant the site's own vocabulary. Called with the dictionary
     pairs the UI already ships, so a word the site can show a Persian reader is
     a word the assistant can understand - with no list here to keep in step. */
  Engine.prototype.vocabulary = function (pairs) {
    if (!Array.isArray(pairs) || !pairs.length) return this;
    this.lexicon = buildLexicon(pairs);
    this.lexiconSize = 0;
    for (var a in this.lexicon.fa) {
      if (Object.prototype.hasOwnProperty.call(this.lexicon.fa, a)) this.lexiconSize++;
    }
    return this;
  };

  Engine.prototype.add = function (doc) {
    if (!doc || !doc.text) return this;
    var text = clean(doc.text);
    if (!text) return this;
    var language = doc.language || (isPersian(text) ? 'fa' : 'en');
    var entry = {
      id: String(doc.id || ('doc-' + this.docs.length)),
      title: clean(doc.title || ''),
      topic: String(doc.topic || 'general'),
      route: String(doc.route || ''),
      language: language,
      text: text
    };
    // Keywords are searchable only: matched, never quoted back.
    entry.keywords = clean(doc.keywords || '');
    entry.tokens = tokenize(entry.title + ' ' + entry.title + ' ' + text + ' ' +
                            entry.keywords);
    entry.length = entry.tokens.length || 1;
    if (!entry.text.length) return this;
    this.docs.push(entry);
    this.corpus[language].push(entry);
    var seen = {};
    for (var i = 0; i < entry.tokens.length; i++) {
      var token = entry.tokens[i];
      if (seen[token]) continue;
      seen[token] = true;
      this.df[language][token] = (this.df[language][token] || 0) + 1;
    }
    return this;
  };

  // Build from whatever the site currently holds. Anything the site does not
  // ship is simply absent — there is no list to keep in sync by hand.
  Engine.prototype.learn = function (source) {
    var site = source || {};
    // Vocabulary first: every later step translates through it.
    this.vocabulary(pairsOf(site.pairs));
    var self = this;
    var docIndex = 0;
    var nextId = function (topic, index) { return topic + '-' + index; };

    function push(topic, title, route, text, language, keywords) {
      var pieces = chunkify(text);
      for (var i = 0; i < pieces.length; i++) {
        self.add({
          id: nextId(topic, docIndex++),
          title: title,
          topic: topic,
          route: route,
          text: pieces[i],
          language: language,
          keywords: i === 0 ? keywords : ''
        });
      }
    }

    var products = Array.isArray(site.products) ? site.products : [];
    if (products.length) {
      // One line that answers "what do you offer" without scraping a grid.
      var live = products.filter(function (product) {
        return product && product.published !== 0 && product.published !== false;
      });
      if (live.length) {
        var names = live.map(function (product) {
          var name = product.title || product.slug || '';
          var summary = clean(product.summary || '');
          return summary ? name + ' — ' + summary : name;
        });
        this.add({
          id: 'catalog-overview',
          title: 'Products',
          topic: 'products',
          route: '#/products',
          text: 'The catalog holds ' + live.length + ' published products. ' + names.join(' | '),
          language: 'en'
        });
      }
    }
    for (var p = 0; p < products.length; p++) {
      var product = products[p];
      if (!product) continue;
      if (product.published === 0 || product.published === false) continue;
      var bits = [product.summary, product.description];
      if (Array.isArray(product.features) && product.features.length) {
        bits.push(product.features.join(' · '));
      }
      if (Array.isArray(product.technologies) && product.technologies.length) {
        bits.push('Technologies: ' + product.technologies.join(', '));
      }
      if (product.status) bits.push('Status: ' + product.status);
      if (product.price_label) bits.push('Price: ' + product.price_label);
      if (product.category) bits.push('Category: ' + product.category);
      push('product',
        (product.title || product.slug || 'Product'),
        '#/products/' + (product.slug || ''),
        bits.filter(Boolean).join('. '));
    }

    var articles = Array.isArray(site.articles) ? site.articles : [];
    for (var a = 0; a < articles.length; a++) {
      var article = articles[a];
      if (!article) continue;
      var body = article.body || article.content || '';
      var text = [article.summary, body].filter(Boolean).join('. ');
      if (article.tags && article.tags.length) text += '. ' + article.tags.join(', ');
      var lang = article.language === 'en' ? 'en' : (isPersian(body + article.title) ? 'fa' : 'en');
      push('article', article.title || article.slug || 'Article',
        '/blog/' + (article.slug || '') + '/', text, lang,
        'مقاله مقالات بلاگ وبلاگ نوشته article articles blog post writing');
    }

    var pages = Array.isArray(site.pages) ? site.pages : [];
    for (var g = 0; g < pages.length; g++) {
      var page = pages[g];
      if (!page) continue;
      // Aliases carry the other language's words for this page, so a Persian
      // question can reach English page copy. They are searchable, never shown.
      push(page.topic || 'page', page.title || '', page.route || '',
        page.text || '', page.language || (isPersian(page.text) ? 'fa' : 'en'),
        page.aliases || '');
    }

    for (var key in this.corpus) {
      if (!this.corpus.hasOwnProperty(key)) continue;
      var list = this.corpus[key];
      var total = 0;
      for (var i = 0; i < list.length; i++) total += list[i].length;
      this.avgLength[key] = list.length ? total / list.length : 1;
    }
    return this;
  };

  Engine.prototype.size = function () { return this.docs.length; };

  // Size per language, so 'no Persian articles yet' is visible rather than a
  // silent empty answer.
  Engine.prototype.stats = function () {
    var topics = {};
    for (var i = 0; i < this.docs.length; i++) {
      topics[this.docs[i].topic] = (topics[this.docs[i].topic] || 0) + 1;
    }
    return {
      chunks: this.docs.length,
      fa: this.corpus.fa.length,
      en: this.corpus.en.length,
      topics: topics
    };
  };

  function idf(engine, language, token) {
    var total = engine.corpus[language].length || 1;
    var docs = engine.df[language][token] || 0;
    return Math.log(1 + (total - docs + 0.5) / (docs + 0.5));
  }

  Engine.prototype.search = function (question, options) {
    var opts = options || {};
    var base = tokenize(question);
    if (!base.length) return [];
    var language = opts.language || (isPersian(question) ? 'fa' : 'en');
    var pool = (language === 'any') ? this.docs : (this.corpus[language] || []);
    if (!pool.length) pool = this.docs;

    // The question's words, plus the site's own translation of each of them.
    var terms = base;
    var engine = this;
    var bridged = expandWith(this.lexicon, terms,
      function (w) { return engine.rarity(w); },
      function (w) { return engine.labelled(w); });

    /* Which of the visitor's words carry the question?

       A word the site mentions everywhere ('website') cannot distinguish one
       page from another: 'قوانین سایت' is a question about the terms, and the
       word 'site' is the setting it was asked in. Rather than naming such words
       in a list, measure them: a term whose matches are spread across most of
       the corpus carries no information, so it is left out of the coverage test.
       The measure comes from the site's own text, so it stays right as the
       content grows. */
    var informative = [];
    for (var w = 0; w < terms.length; w++) {
      // How far this one word spreads, counting only its own translation.
      var direct = (this.lexicon.fa && this.lexicon.fa[terms[w]]) ||
                   (this.lexicon.en && this.lexicon.en[terms[w]]);
      var reach = this.reach(terms[w], direct ? [direct] : []);
      if (reach === 0) {
        // Absent from the text. It is still the subject if the site's
        // dictionary knows the word - the English page copy just cannot
        // contain it. Otherwise it is a word the site never says.
        if (this.known(terms[w])) informative.push(terms[w]);
      } else if (reach < 0.6 * this.docs.length) {
        informative.push(terms[w]);
      }
      // reach >= 60% of the corpus: background vocabulary, not the subject.
    }
    var meaningful = Math.max(1, informative.length);

    var phrase = fold(String(question)).toLowerCase().replace(/\s+/g, ' ').trim();
    var ranked = [];
    for (var i = 0; i < pool.length; i++) {
      var doc = pool[i];
      var counts = {};
      for (var j = 0; j < doc.tokens.length; j++) {
        var token = doc.tokens[j];
        counts[token] = (counts[token] || 0) + 1;
      }
      var score = 0;
      var matched = 0;
      var ownMatched = 0;
      var strongMatched = 0;

      // Which search words this chunk contains, and which of the visitor's
      // words each of them stands for. A translation counts as reaching the
      // visitor's word: the chunk answers 'قیمت' by talking about price.
      var covered = [];
      var sum = 0;
      function weigh(term, weight) {
        var freq = counts[term];
        if (!freq) return false;
        var norm = doc.length / (this.avgLength[doc.language] || 1);
        sum += weight * idf(this, doc.language, term) *
          ((freq * (this.k1 + 1)) / (freq + this.k1 * (1 - this.b + this.b * norm)));
        return true;
      }
      var self = this;

      for (var t = 0; t < terms.length; t++) {
        // A word the visitor typed outranks a word the dictionary supplied.
        if (weigh.call(self, terms[t], 1)) {
          matched++;
          ownMatched++;
          strongMatched++;
          if (covered.indexOf(terms[t]) === -1) covered.push(terms[t]);
        }
      }
      for (var b = 0; b < bridged.length; b++) {
        var word = bridged[b];
        if (!weigh.call(self, word, 0.85)) continue;
        matched++;
        strongMatched++;
        // Attribute the hit to every visitor word this translation stands for.
        for (var a = 0; a < terms.length; a++) {
          var mapped = (self.lexicon.fa && self.lexicon.fa[terms[a]]) ||
                       (self.lexicon.en && self.lexicon.en[terms[a]]);
          var partnerHit = mapped === word;
          if (!partnerHit && self.lexicon.known && self.lexicon.known[terms[a]]) {
            partnerHit = self.lexicon.known[terms[a]].indexOf(word) !== -1;
          }
          if (partnerHit && covered.indexOf(terms[a]) === -1) covered.push(terms[a]);
        }
      }
      score = sum;

      var ownHits = 0;
      for (var c = 0; c < informative.length; c++) {
        if (covered.indexOf(informative[c]) !== -1) ownHits++;
      }

      if (!matched) continue;
      /* A chunk that contains a translation but none of the visitor's own words
         is weaker evidence than one that contains what they typed. Keep it, but
         demote it, so a fallback translation can never outrank a direct hit:
         'AURION' must reach the passage that says AURION, not one that only
         happens to share a translated word with the question. */
      if (ownMatched === 0) score *= 0.35;

      var total = terms.length + bridged.length;
      score *= 1 + 0.45 * (matched / total);
      if (matched === total) score *= 1.18;
      if (phrase.length > 3 && doc.text.toLowerCase().indexOf(phrase) !== -1) score *= 1.55;
      // The page's own label is the strongest signal of its subject: a word in
      // the title/topic describes the page, a word in the body may be incidental
      // ('order date' inside a refund policy).
      var labelFolded = fold(doc.title + ' ' + doc.topic + ' ' + (doc.keywords || '')).toLowerCase();
      var labelHits = 0;
      var allTerms = terms.concat(bridged);
      for (var q = 0; q < allTerms.length; q++) {
        if (labelFolded.indexOf(allTerms[q]) !== -1) labelHits++;
      }
      if (labelHits && allTerms.length) {
        score *= 1 + 1.8 * (labelHits / allTerms.length);
      }

      ranked.push({
        doc: doc, score: score, matched: matched,
        ownMatched: ownMatched,
        strongMatched: strongMatched,
        // Coverage is about the visitor's own words: a translation is evidence
        // that the site can talk about the subject, not that this chunk
        // answered this question.
        coverage: Math.min(1, ownHits / meaningful)
      });
    }
    ranked.sort(function (left, right) { return right.score - left.score; });
    return ranked.slice(0, opts.limit || this.maxResults);
  };

  /* How much of the corpus a word reaches, counting its translation. Used to
     tell the subject of a question from the setting it was asked in. */
  Engine.prototype.reach = function (term, bridged) {
    var seen = {};
    var total = 0;
    var words = [term];
    for (var b = 0; b < (bridged || []).length; b++) {
      if (words.indexOf(bridged[b]) === -1) words.push(bridged[b]);
    }
    for (var i = 0; i < this.docs.length; i++) {
      var doc = this.docs[i];
      var hit = false;
      for (var w = 0; w < words.length; w++) {
        if (doc.tokens.indexOf(words[w]) === -1) continue;
        hit = true;
        break;
      }
      if (!hit) continue;
      seen[doc.id] = true;
      total++;
    }
    return total;
  };

  /* Is this word part of the site's subject matter at all?

     Two kinds of evidence, both from the site: the word appears in something it
     publishes, or the site's own dictionary pairs it with something that does.
     'قیمت' never appears in the English page copy, but the site's dictionary
     translates price strings containing it, and the catalog says 'Request a
     quote' - so price is a subject this site covers, and a price question
     deserves an answer from the terms page rather than a claim of ignorance. */
  Engine.prototype.known = function (term) {
    // The word itself, or the site's one-to-one translation of it.
    var direct = (this.lexicon.fa && this.lexicon.fa[term]) ||
                 (this.lexicon.en && this.lexicon.en[term]);
    if (this.reach(term, direct ? [direct] : []) > 0) return true;
    var self = this;
    /* A phrase pair is weaker: the site says both sides describe the same
       thing, so a word that shares a phrase with something the corpus contains
       is plausibly part of the site's subject. Used only to decide whether to
       search, never to claim coverage - and limited to the top partner, because
       a long phrase full of ordinary words would make anything look known. */
    var partners = this.lexicon.known && this.lexicon.known[term];
    if (!partners || !partners.length) return false;
    return this.reach(partners[0], []) > 0;
  };

  /* Is the best hit strong enough to answer with?

     Raw BM25 score is not a usable gate: it depends on corpus size, so a
     threshold tuned on the live site rejects everything on a small one. The
     question that actually matters is *which* words were left unanswered.

     A term the site never mentions anywhere is the honest reason to refuse:
     "قیمت سایت چقدر است" reduces to [قیمت, سایت]; the site talks about websites
     constantly, and never about price - so the visitor is asking about
     something the site does not cover, and the answer must say so.

     Conversely, "چرا سرعت مهم است" reduces to [سرعت, مهم]; 'مهم' never appears
     either, but 'سرعت' does and it is the subject. Refusing that would be
     unhelpful. So the rule is per-term: a missing term refuses the answer only
     when a matched term is common.

     Language is not part of this test. The site's page copy is English and much
     of its catalog copy is Persian, so a Persian question will often only match
     English text — refusing it because the language differs would leave Xiona
     mute on half the site. */
  Engine.prototype._judge = function (best) {
    if (!best) return true;
    if (best.score < this.minScore) return true;
    // coverage already ignores the words that describe the setting rather than
    // the subject, so it is the honest measure of "did I answer the question".
    return best.coverage < 0.5;
  };

  /* ------------------------------------------------------------- answering */

  // \b is ASCII-only in JavaScript, so it never fires after a Persian letter.
  // The greeting test therefore anchors at the start and checks the token.
  var GREETING = /^(hi|hello|hey|salam|سلام|درود|وقت بخیر|چطوری|خوبی)(\s|$|[!,.؟?])/i;

  function languageOf(text) { return isPersian(text) ? 'fa' : 'en'; }

  // Sentences that only make sense inside their own page ("open Products").
  // Kept because they are useful, dropped when a chunk is quoted out of context.
  function tidy(text) {
    return String(text || '')
      // UI glyphs from the page templates ('Request this product ↗', '✓', '⌘')
      // are not part of a sentence.
      .replace(/[↗←→✓⌘▣✕×]/g, ' ')
      .replace(/\s+/g, ' ')
      // Collapse the doubled full stop that appears when a source string
      // already ends in '.' and is joined with '. '.
      .replace(/\.{2,}/g, '.')
      .replace(/\.\s*,/g, ',')
      // A leading full stop is left behind when a chunk starts on the separator
      // a template put between blocks.
      .replace(/^[\s.,;:]+/, '')
      .replace(/\.\s*\./g, '.')
      // A one-word label followed by a full stop ('Overview.') is a heading the
      // template rendered as a sentence; join it to what it introduces.
      .replace(/\b([A-Z][a-z]{2,12})\.\s+(?=[A-Z])/g, '$1: ')
      .replace(/\s+([.,;:!?؟])/g, '$1')
      .trim();
  }

  /* The translations of a question that a given chunk actually contains. Used
     to rank the chunk's own sentences when the visitor's language is not the
     language the page is written in. */
  function matchedWords(doc, terms, engine, bridged) {
    var out = [];
    function take(word) {
      if (word && out.indexOf(word) === -1 && doc.tokens.indexOf(word) !== -1) out.push(word);
    }
    for (var i = 0; i < terms.length; i++) take(terms[i]);
    /* The words the search actually used. For a Persian question about English
       copy those are the translations - including the ones the site's phrase
       evidence supplied rather than a clean one-to-one mapping. Ranking the
       chunk's sentences on the visitor's words alone finds nothing to rank. */
    var all = (bridged || []).slice(0);
    for (var b = 0; b < all.length; b++) take(all[b]);
    return out;
  }

  // Pick the sentences of a chunk that actually carry the answer, so a long
  // AURION paragraph does not arrive whole when only one line was asked for.
  function focus(text, terms, budget) {
    var parts = sentences(text).filter(function (part) {
      // Section headings ('How to request support', 'Review and next steps') are
      // labels, not sentences. Starting an answer with one misleads about the
      // subject, so they are dropped when shorter than a clause.
      return !(part.length < 48 && part.split(' ').length <= 6 && !/[.؟?!]$/.test(part));
    });
    if (!parts.length) return tidy(text);
    if (parts.length === 1) return tidy(parts[0]);
    /* Rank the sentences of the chunk. Counting which search words each one
       contains is not enough: 'Scope, price and milestones' and 'a fixed-price
       contract' both contain 'price', so the tie falls to whichever came first.
       A sentence that mentions the rare word the question is actually about is
       the better lead, so a term's weight is its rarity inside this chunk. */
    var weight = {};
    for (var t = 0; t < terms.length; t++) {
      var seen = 0;
      for (var c = 0; c < parts.length; c++) {
        if (tokenize(parts[c]).indexOf(terms[t]) !== -1) seen++;
      }
      weight[terms[t]] = seen ? 1 / seen : 0;
    }
    var scored = [];
    for (var i = 0; i < parts.length; i++) {
      var tokens = tokenize(parts[i]);
      var hits = 0;
      for (var t2 = 0; t2 < terms.length; t2++) {
        if (tokens.indexOf(terms[t2]) !== -1) hits += weight[terms[t2]] || 0;
      }
      scored.push({ index: i, hits: hits });
    }
    scored.sort(function (a, b) { return b.hits - a.hits || a.index - b.index; });
    var keep = [];
    var used = 0;
    for (var s = 0; s < scored.length; s++) {
      var part = parts[scored[s].index];
      if (used + part.length > budget && keep.length) break;
      keep.push(scored[s].index);
      used += part.length;
      if (used > budget * 0.62) break;
    }
    // Lead with the sentence that answered the question, then its neighbours in
    // reading order. Opening with whatever came first made a correct retrieval
    // read like an unrelated paragraph.
    var lead = keep.length ? keep[0] : 0;
    keep.sort(function (a, b) { return a - b; });
    keep.sort(function (a, b) {
      if (a === lead) return -1;
      if (b === lead) return 1;
      return a - b;
    });
    return tidy(keep.map(function (index) { return parts[index]; }).join(' '));
  }

  /* The words of a question that appear nowhere in the corpus. A question made
     entirely of such words is about something this site does not publish. */
  Engine.prototype.absentTerms = function (terms) {
    var out = [];
    for (var i = 0; i < terms.length; i++) {
      if (this.known(terms[i])) continue;
      if (out.indexOf(terms[i]) === -1) out.push(terms[i]);
    }
    return out;
  };

  /* Does a word the site knows actually answer this question, or is it only the
     frame around an unknown subject? 'ربات' is unknown, and 'شما'/'هستید' carry
     nothing, so the question is about a robot and the site has no robot to
     describe beyond the panel text it publishes. */
  /* Is an unknown word accounted for by a word the question also contains?
     'هزینه بازپرداخت': the refund page explains what a refund costs, so the
     cost word is answered by the refund word. 'بودجه شروع': nothing on this site
     connects a budget to starting, so the budget stands unexplained. */
  Engine.prototype.explained = function (word, terms, absent) {
    for (var i = 0; i < terms.length; i++) {
      var other = terms[i];
      if (other === word || absent.indexOf(other) !== -1) continue;
      // Do the two occur together anywhere in the site's own strings?
      var pairs = this.lexicon.known && this.lexicon.known[other];
      if (pairs && pairs.length && this.lexicon.known[word]) {
        var mine = this.lexicon.known[word];
        for (var p = 0; p < mine.length; p++) {
          if (pairs.indexOf(mine[p]) !== -1) return true;
        }
      }
    }
    return false;
  };

  Engine.prototype.carriesQuestion = function (terms, absent) {
    var known = [];
    for (var i = 0; i < terms.length; i++) {
      if (absent.indexOf(terms[i]) === -1) known.push(terms[i]);
    }
    if (!known.length) return false;
    // A known word answers only if the site has real text behind it - more than
    // a single incidental mention.
    for (var k = 0; k < known.length; k++) {
      var direct = (this.lexicon.fa && this.lexicon.fa[known[k]]) ||
                   (this.lexicon.en && this.lexicon.en[known[k]]);
      var scope = this.reach(known[k], direct ? [direct] : []);
      if (scope >= 1) return true;
    }
    return false;
  };

  /* The subjects the index actually covers, taken from the documents themselves
     rather than a list here. Used when the assistant has to say what it can
     talk about, so that sentence is always true. */
  Engine.prototype.topics = function () {
    var seen = {};
    var out = [];
    for (var i = 0; i < this.docs.length; i++) {
      var doc = this.docs[i];
      if (!doc.title) continue;
      if (doc.topic === 'article') continue;
      if (seen[doc.topic]) continue;
      seen[doc.topic] = true;
      out.push(doc.title);
    }
    return out;
  };

  var LABELS = {
    fa: {
      from: 'از',
      more: 'بیشتر بخوانید',
      ask: 'سؤال دیگری بپرسید',
      unsure: 'پاسخ تأییدشده‌ای برای این سؤال پیدا نکردم.',
      nodocs: 'هنوز دانشی برای پاسخ دادن ندارم. وقتی محصول یا مقاله‌ای منتشر شود، Xiona آن را می‌خواند و پاسخ می‌دهد.',
      greeting: 'سلام. من Xiona هستم؛ دستیار همین سایت.',
      html: 'این سایت در مرحلهٔ توسعه است.'
    },
    en: {
      from: 'From',
      more: 'Read more',
      ask: 'Ask something else',
      unsure: "I couldn't find an answer to that on this site.",
      nodocs: "I have no knowledge yet. Once a product or article is published, Xiona reads it and can answer from it.",
      greeting: "Hi, I'm Xiona — this site's own assistant.",
      html: 'This site is in development.'
    }
  };

  /* Say plainly that the site does not cover a subject, and name what it does
     cover - from the index, so the sentence cannot go stale. */
  function uncoveredText(absent, language, topics) {
    var join = language === 'fa' ? '، ' : ', ';
    var subject = absent.join(join);
    var list = topics.slice(0, 5).join(join);
    if (language === 'fa') {
      return 'این سایت دربارهٔ «' + subject + '» چیزی منتشر نکرده است، پس پاسخ تأییدشده‌ای ندارم.' +
             (list ? ' آنچه منتشر شده: ' + list + '.' : '') +
             ' می‌توانید پرسش خود را از صفحهٔ «شروع پروژه» مطرح کنید.';
    }
    return 'This site does not publish anything about "' + subject +
           '", so I have no answer for it.' +
           (list ? ' What it does publish: ' + list + '.' : '') +
           ' You can raise it on the Start a project page.';
  }

  Engine.prototype.answer = function (question, options) {
    var opts = options || {};
    var query = String(question || '').trim();
    var language = languageOf(query);
    var labels = LABELS[language];
    if (!query) {
      return { text: labels.unsure, source: 'empty', language: language, citations: [] };
    }
    if (!this.size()) {
      return { text: labels.nodocs, source: 'empty-index', language: language, citations: [] };
    }
    if (GREETING.test(query) && tokenize(query).length <= 2) {
      return { text: labels.greeting, source: 'greeting', language: language, citations: [] };
    }

    var terms = tokenize(query);

    /* Before searching, establish what the visitor is asking about and whether
       this site has anything to say on it.

       There used to be two regex tables here - one matching price wording, one
       matching "are you a bot" - that returned a ready-made sentence. That is
       not answering; it is reciting. It also got the question wrong: 'پروژه
       چقدر طول می‌کشد' (how long does a project take) matched the price table
       because both contain 'چقدر', so a question about duration was answered
       with a sentence about pricing, while the retrieval step that had already
       found the right page was never reached.

       The replacement asks the only question that can be settled from the
       site's own text: is the word this question hangs on present anywhere in
       what this site publishes? If a word is absent from every chunk, the site
       does not cover it, and saying so is honest. If it is present, we search
       it and the content answers. */
    /* A question names something; the rest is the frame it is asked in.
       'بودجه لازم برای شروع چقدر است' asks about a budget, and mentions
       starting as the context. If none of the words the site knows is carrying
       the question - if the ONLY thing it would be answering about is a word
       the site never publishes - then it has nothing to say, even though the
       supporting words are familiar. */
    /* An unknown word is not always a refusal: 'هزینه بازپرداخت' names cost,
       which this site does not publish, but its subject is the refund, which it
       does. The distinction is which side of the question the word sits on. A
       word the site never uses, that no known word of the question explains, is
       the subject - and then saying "I have nothing on that" is the answer. */
    /* A question with no content words left is a question about the assistant
       itself: 'شما کی هستید' is entirely pronoun and copula, and the site does
       publish what this assistant is - in the panel text it shows the visitor.
       Answering from that chunk is answering from the site, not from a script. */
    if (!terms.length) {
      // The site's own description of this assistant is the chunk that was read
      // from the panel. Look it up by topic so a stray match on 'support' in the
      // privacy page cannot answer a question about identity.
      var self = [];
      for (var d = 0; d < this.docs.length; d++) {
        if (this.docs[d].topic === 'assistant') {
          self = [{ doc: this.docs[d], score: 1 }];
          break;
        }
      }
      if (!self.length) self = this.search('Xiona assistant', { language: 'any', limit: 1 });
      if (self.length) {
        return {
          text: focus(self[0].doc.text, [], 320),
          source: 'knowledge',
          language: language,
          citations: [{ title: self[0].doc.title, route: self[0].doc.route,
                        topic: self[0].doc.topic, score: Math.round(self[0].score * 100) / 100 }]
        };
      }
      return { text: labels.unsure, source: 'no-match', language: language, citations: [] };
    }

    var absent = this.absentTerms(terms);
    var subjectMissing = false;
    for (var a = 0; a < absent.length; a++) {
      if (!this.explained(absent[a], terms, absent)) { subjectMissing = true; break; }
    }
    if (absent.length && (absent.length === terms.length || subjectMissing) &&
        !this.carriesQuestion(terms, absent)) {
      return {
        text: uncoveredText(absent, language, this.topics()),
        source: 'uncovered',
        language: language,
        citations: [],
        absent: absent
      };
    }
    // Search the whole index, always. The site's page copy is English and much
    // of its catalog is Persian, so language is a weak signal: preferring the
    // question's own language made a Persian question match the one Persian
    // article and stop, ignoring the page that actually answered it.
    var hits = this.search(query, { language: 'any', limit: this.maxResults });
    if (this._judge(hits[0])) {
      return { text: labels.unsure, source: 'no-match', language: language, citations: [] };
    }

    var parts = [];
    var citations = [];
    var seen = {};
    // Only chunks close to the best one: three mediocre matches pasted together
    // read like a paragraph that wandered off. A strong lead plus one supporting
    // passage is an answer; five weak ones are noise.
    var floor = hits[0].score * 0.55;
    for (var i = 0; i < hits.length; i++) {
      var hit = hits[i];
      if (i > 0 && hit.score < floor) break;
      if (seen[hit.doc.topic + ':' + hit.doc.title]) continue;
      seen[hit.doc.topic + ':' + hit.doc.title] = true;
      /* Sentences are ranked against the words that actually occur in this
         chunk - the visitor's own words plus the translations the chunk
         contains. Ranking on the visitor's words alone means an English page
         answers a Persian question with whichever sentence happens to come
         first. */
      var budget = 340;
      var engine = this;
      var used = expandWith(this.lexicon, terms,
        function (w) { return engine.rarity(w); },
        function (w) { return engine.labelled(w); });
      var body = focus(hit.doc.text, matchedWords(hit.doc, terms, this, used), budget);
      if (!body) continue;
      parts.push(body);
      citations.push({
        title: hit.doc.title,
        route: hit.doc.route,
        topic: hit.doc.topic,
        score: Math.round(hit.score * 100) / 100
      });
      if (parts.join(' ').length > 700) break;
    }

    return {
      text: parts.join(' '),
      source: 'knowledge',
      language: language,
      citations: citations
    };
  };

  /* ----------------------------------------------------------- site reader */

  // The assistant learns from the pages the app renders. The app calls this
  // after every render, so opening a page teaches Xiona its text - there is no
  // second copy of the site copy to drift out of date.
  var PAGE_TITLES = {
    '/': ['home', 'Home'],
    '/products': ['products', 'Products'],
    '/services': ['services', 'Services'],
    '/about': ['about', 'About AXIASOFT'],
    '/contact': ['contact', 'Start a project'],
    '/aurion': ['aurion', 'AURION'],
    '/privacy': ['privacy', 'Privacy policy'],
    '/terms': ['terms', 'Terms and conditions'],
    '/refunds-policy': ['refunds-policy', 'Refund and return policy']
  };

  function readSite(options) {
    var opts = options || {};
    var win = opts.window || (typeof window !== 'undefined' ? window : null);
    var doc = opts.document || (win ? win.document : null);
    var source = {
      products: opts.products || [],
      articles: opts.articles || [],
      pages: (opts.pages || []).slice()
    };
    if (!doc) return source;

    var container = opts.container || doc.querySelector('#app');
    if (!container) return source;
    var path = String(opts.path || (win && win.location ? win.location.hash : '') || '')
      .replace(/^#/, '').split('?')[0] || '/';
    var meta = PAGE_TITLES[path];
    var text = (container.textContent || '').replace(/\s+/g, ' ').trim();
    if (meta && text.length > 120) {
      source.pages.push({
        topic: meta[0],
        title: meta[1],
        route: '#' + path,
        text: text
      });
    }
    return source;
  }

  // Learn everything the site ships: the catalog snapshot, the articles, and
  // the sections that live in the page shell rather than a rendered route.
  /* Has the page-level knowledge (footer, panel text) been added yet? The app
     re-learns after every render, and adding the same chunks repeatedly would
     dilute the index. */
  Engine.prototype.learnSite = function (options) {
    var opts = options || {};
    // The app calls this after every render. Re-indexing the whole site each
    // time would multiply every chunk and skew the statistics, so the data load
    // happens once; the caller adds a newly visited page itself.
    if (this.hasSite) {
      var again = opts.site || {};
      if (again.pages && again.pages.length) this.learn({ pages: again.pages });
      return this;
    }
    this.hasSite = true;
    var win = opts.window || (typeof window !== 'undefined' ? window : null);
    var doc = opts.document || (win ? win.document : null);
    var static_ = (win && win.AXIA_STATIC) || {};
    var args = {
      window: win,
      document: doc,
      products: opts.products || (Array.isArray(static_.products) ? static_.products : []),
      articles: opts.articles || (Array.isArray(static_.articles) ? static_.articles : []),
      // Page copy the build rendered from the app's own templates. Without it
      // the assistant only knows the pages this visitor happened to open.
      pages: opts.pages || (Array.isArray(static_.pages) ? static_.pages : []),
      // The site's own Persian/English dictionary, emitted by the build.
      pairs: opts.pairs || (Array.isArray(static_.pairs) ? static_.pairs : [])
    };
    this.learn(args);
    if (!doc) return this;
    // Footer and header carry the studio's own description on every page.
    var footer = doc.querySelector('footer .footer-top > p');
    if (footer) {
      this.add({
        id: 'shell-footer', title: 'AXIASOFT', topic: 'about', route: '#/about',
        text: footer.textContent || ''
      });
    }
    /* What this assistant is, in the words the site shows the visitor. Read it
       from the page when the panel is open, and otherwise fall back to the
       template string the app carries - so 'who are you' is answered by the same
       sentence a visitor can read above the chat box, and the two cannot drift.
       This is the site describing itself, not a scripted reply. */
    var claims = [];
    var nodes = doc.querySelectorAll('.chat-head strong, .chat-head small, .chat-disclaimer');
    for (var n = 0; n < nodes.length; n++) {
      var text = (nodes[n].textContent || '').trim();
      if (text) claims.push(text);
    }
    if (claims.length) {
      this.add({
        id: 'shell-assistant', title: 'Xiona', topic: 'assistant', route: '#/contact',
        text: claims.join('. '),
        keywords: 'assistant bot ai robot made built who xiona دستیار ربات هوش مصنوعی کی ساخت'
      });
    }
    return this;
  };

  return {
    Engine: Engine,
    readSite: readSite,
    tokenize: tokenize,
    fold: fold,
    isPersian: isPersian,
    labels: LABELS
  };
});
