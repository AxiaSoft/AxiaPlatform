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

  var STOPWORDS = {
    fa: ['و', 'در', 'به', 'از', 'که', 'این', 'را', 'با', 'است', 'برای', 'آن',
      'یک', 'خود', 'تا', 'کرد', 'بر', 'هم', 'نیز', 'یا', 'شد', 'شده', 'های',
      'ها', 'می', 'شود', 'بود', 'اما', 'اگر', 'چه', 'کی', 'چطور', 'چگونه',
      'کجا', 'چقدر', 'آیا', 'دارید', 'دارم', 'دارد', 'کنم', 'کنید', 'کنم',
      'شما', 'ما', 'من', 'او', 'آنها', 'همه', 'بیشتر', 'خیلی', 'چیست', 'چیه',
      'چرا', 'آیا', 'باید', 'توانم', 'توانید', 'می‌توانم', 'می‌توانید', 'هست',
      'هستند', 'هستم', 'نیست', 'بوده', 'دارند', 'لطفا', 'لطفاً', 'بگو',
      'بگویید', 'بگید', 'میخوام', 'می‌خواهم', 'خواستم'],
    en: ['the', 'a', 'an', 'is', 'are', 'was', 'were', 'do', 'does', 'did',
      'how', 'what', 'when', 'where', 'who', 'why', 'can', 'could', 'would',
      'should', 'i', 'you', 'we', 'they', 'it', 'of', 'to', 'in', 'on', 'for',
      'with', 'and', 'or', 'but', 'my', 'your', 'our', 'me', 'us', 'them',
      'this', 'that', 'these', 'those', 'be', 'been', 'have', 'has', 'had',
      'there', 'about', 'tell', 'please', 'want', 'need', 'get', 'got']
  };

  /* The site publishes its page copy in English and much of its catalog copy in
     Persian. A visitor asks in one language; the answer may only exist in the
     other. This bridge is small and hand-checked on purpose: it maps the words
     a visitor actually uses to the words the site uses, so a Persian question
     reaches English text. It is a lexicon, not a translator - it never produces
     prose, only search terms. */
  var BRIDGE = {
    // fa -> en
    'محصول': ['product', 'products', 'catalog'],
    'محصولات': ['product', 'products', 'catalog'],
    'کاتالوگ': ['catalog', 'products'],
    'سفارش': ['order', 'request', 'project'],
    'درخواست': ['request', 'order'],
    'پروژه': ['project', 'work'],
    'ثبت': ['place', 'submit'],
    'سفارش_ثبت': ['place an order', 'start a project', 'request'],
    'شروع': ['start', 'begin', 'request'],
    'قیمت': ['price', 'cost', 'quote'],
    'هزینه': ['cost', 'price', 'quote'],
    'پیش‌فاکتور': ['quote', 'quotation'],
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
    'صفحه': ['page', 'section'],
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
    // en -> fa
    'product': ['محصول'], 'products': ['محصولات'], 'order': ['سفارش'],
    'request': ['درخواست'], 'project': ['پروژه'], 'price': ['قیمت'],
    'cost': ['هزینه'], 'refund': ['بازپرداخت'], 'services': ['خدمات'],
    'support': ['پشتیبانی'], 'privacy': ['حریم'], 'terms': ['قوانین'],
    'about': ['درباره'], 'contact': ['تماس'], 'website': ['وب‌سایت'],
    'article': ['مقاله'], 'blog': ['وبلاگ'], 'speed': ['سرعت'],
    'security': ['امنیت'], 'payment': ['پرداخت'], 'account': ['حساب']
  };

  // Words that limit *what* is being asked ("which products", "how much"). They
  // are worth searching for but must not decide relevance on their own.
  /* Words that describe the setting rather than the subject. 'قوانین سایت' is a
     question about the terms, not about websites. */
  var VAGUE = ['website', 'web', 'site', 'page', 'section', 'company', 'about',
    'product', 'products', 'service', 'services'];

  var GENERIC = {
    fa: ['محصول', 'محصولات', 'کاتالوگ', 'خدمات'],
    en: ['product', 'products', 'service', 'services', 'catalog']
  };

  /* Phrase-level bridges: a visitor does not ask about a verb, they ask about a
     task. "سفارش ثبت کنم" is "place an order", not "register" + "request", and
     matching the phrase is what keeps a refund page from answering it. */
  /* A site with no prices on it cannot answer a price question. Saying so is
     the correct answer, and it is better than a nearby paragraph about
     websites. These topics are refused explicitly instead of being scored. */
  var UNCOVERED = [
    [/قیمت|هزینه|چقدر|تعرفه|price|cost|pricing|how much/i, {
      fa: 'قیمت‌ها روی این سایت منتشر نشده‌اند. دامنه و هزینه پس از بررسی درخواست شما توافق می‌شود؛ می‌توانید از صفحهٔ تماس درخواست بفرستید.',
      en: 'Prices are not published on this site. Scope and cost are agreed after your request is reviewed — the Start a project page is the way in.'
    }],
    [/ربات|هوش مصنوعی هستی|are you (an? )?(ai|bot|robot)|who made you|چه کسی تو را ساخت/i, {
      fa: 'من Xiona هستم، دستیار همین سایت. کاملاً داخل مرورگر شما اجرا می‌شوم؛ از محتوای منتشرشدهٔ AXIASOFT یاد می‌گیرم و به هیچ سرویس بیرونی وصل نیستم.',
      en: "I'm Xiona, this site's assistant. I run entirely in your browser, learn from what AXIASOFT publishes, and am not connected to any outside service."
    }]
  ];

  var PHRASES = [
    [/(سفارش|درخواست).*(ثبت|بدم|بدهم|کنم)|چطور.*(سفارش|درخواست)/, ['place an order', 'start a project', 'request', 'order']],
    [/بازپرداخت|پس دادن پول|استرداد/, ['refund', 'cancellation']],
    [/حریم خصوصی|اطلاعات من/, ['privacy', 'data protection']],
    [/قوانین|شرایط استفاده/, ['terms', 'conditions']],
    [/با انسان|پشتیبان انسانی|آدم واقعی/, ['human', 'support', 'person']],
    [/قیمت|هزینه|چقدر/, ['price', 'cost', 'quote']],
    [/محصولات|چه چیزی می‌فروشید/, ['products', 'catalog']]
  ];

  /* Expand a question's terms across languages so a Persian question can reach
     English text and the other way round. Original terms come first and are
     weighted by the caller; bridged terms only add reach. */
  function expand(terms, language, question) {
    var out = terms.slice();
    var extra = [];
    var folded = fold(String(question || '')).toLowerCase();
    for (var k = 0; k < PHRASES.length; k++) {
      if (!PHRASES[k][0].test(folded)) continue;
      var words = PHRASES[k][1];
      for (var w = 0; w < words.length; w++) {
        if (out.indexOf(words[w]) === -1 && extra.indexOf(words[w]) === -1) extra.push(words[w]);
      }
    }
    for (var i = 0; i < terms.length; i++) {
      var mapped = BRIDGE[terms[i]];
      if (!mapped) continue;
      for (var j = 0; j < mapped.length; j++) {
        var word = mapped[j];
        if (out.indexOf(word) === -1 && extra.indexOf(word) === -1) extra.push(word);
      }
    }
    return { terms: out, bridged: extra };
  }

  // Persian suffixes that carry little meaning on their own. Stripping them is
  // the difference between 'محصولات' and 'محصول' matching, and they not matching.
  var FA_SUFFIXES = ['هایشان', 'هایمان', 'هایتان', 'هایش', 'هایم', 'هایت',
    'های', 'هایی', 'ها', 'تر', 'ترین', 'شان', 'مان', 'تان', 'یی', 'یم', 'ید',
    'ند', 'هاست', 'ای', 'ی'];

  function isPersian(text) {
    return /[\u0600-\u06FF]/.test(String(text || ''));
  }

  function fold(text) {
    var out = '';
    var src = String(text || '');
    for (var i = 0; i < src.length; i++) {
      var ch = src.charAt(i);
      out += FOLD[ch] || ch;
    }
    // Persian diacritics (fathatan .. sukun) and the ZWNJ carry no meaning for
    // matching, and ZWNJ in particular splits words the user did not split.
    // \u061F (Arabic question mark) and \u060C (comma) live inside the Arabic
    // block, so a naive token regex keeps them glued to the word: 'چیست؟'
    // stays one token and never matches 'چیست'.
    return out.replace(/[\u064B-\u0652\u0670\u0640\u200c\u200f\u200e\u061F\u060C\u061B]/g, ' ');
  }

  function stripSuffix(word) {
    if (!isPersian(word) || word.length <= 3) return word;
    for (var i = 0; i < FA_SUFFIXES.length; i++) {
      var suffix = FA_SUFFIXES[i];
      if (word.length - suffix.length >= 3 && word.slice(-suffix.length) === suffix) {
        return word.slice(0, -suffix.length);
      }
    }
    return word;
  }

  function lightStem(word) {
    if (!isPersian(word)) {
      // English: enough stemming for 'pricing'/'prices'/'priced' to meet.
      return word.replace(/(ies)$/, 'y').replace(/(ses|xes|ches|shes)$/, 's')
                 .replace(/(ing|ed|es|s)$/, '');
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
      if (stem.length < 2) continue;
      out.push(stem);
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
  }

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

    // The question's own words, plus their counterparts in the other language.
    var expanded = expand(base, language, question);
    var terms = expanded.terms;
    var bridged = expanded.bridged;
    var generic = GENERIC[language] || [];
    // Coverage is judged on the words that carry the question. 'سایت' is where
    // the visitor is, not what they are asking about.
    var vagueOwn = 0;
    for (var v = 0; v < terms.length; v++) {
      if (VAGUE.indexOf(terms[v]) !== -1 || generic.indexOf(terms[v]) !== -1) vagueOwn++;
    }
    var meaningful = Math.max(1, terms.length - vagueOwn);

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
      function add(term, weight) {
        var freq = counts[term];
        if (!freq) return false;
        var norm = doc.length / (this.avgLength[doc.language] || 1);
        score += weight * idf(this, doc.language, term) *
          ((freq * (this.k1 + 1)) / (freq + this.k1 * (1 - this.b + this.b * norm)));
        return true;
      }
      var self = this;
      for (var t = 0; t < terms.length; t++) {
        // A word the visitor typed outranks a word the bridge supplied.
        if (add.call(self, terms[t], 1)) {
          matched++;
          ownMatched++;
          if (generic.indexOf(terms[t]) === -1) strongMatched++;
        }
      }
      for (var b = 0; b < bridged.length; b++) {
        // A bridged word that names a section ('terms', 'privacy') is specific;
        // one that names the medium ('website') is not. Weight accordingly.
        var weight = VAGUE.indexOf(bridged[b]) === -1 ? 0.85 : 0.45;
        if (add.call(self, bridged[b], weight)) {
          matched++;
          if (generic.indexOf(bridged[b]) === -1 && VAGUE.indexOf(bridged[b]) === -1) strongMatched++;
        }
      }
      if (!matched) continue;

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
        coverage: Math.min(1, strongMatched / meaningful)
      });
    }
    ranked.sort(function (left, right) { return right.score - left.score; });
    return ranked.slice(0, opts.limit || this.maxResults);
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
    var scored = [];
    for (var i = 0; i < parts.length; i++) {
      var tokens = tokenize(parts[i]);
      var hits = 0;
      for (var t = 0; t < terms.length; t++) {
        if (tokens.indexOf(terms[t]) !== -1) hits++;
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

  var LABELS = {
    fa: {
      from: 'از',
      more: 'بیشتر بخوانید',
      ask: 'سؤال دیگری بپرسید',
      unsure: 'پاسخ تأییدشده‌ای برای این سؤال پیدا نکردم. Xiona فقط از محتوای همین سایت پاسخ می‌دهد؛ می‌توانم دربارهٔ محصولات، خدمات، فرایند سفارش، AURION، مقالات یا قوانین بازپرداخت کمک کنم.',
      nodocs: 'هنوز دانشی برای پاسخ دادن ندارم. وقتی محصول یا مقاله‌ای منتشر شود، Xiona آن را می‌خواند و پاسخ می‌دهد.',
      greeting: 'سلام. من Xiona هستم؛ دستیار همین سایت. از محتوای منتشرشدهٔ AXIASOFT یاد می‌گیرم و مستقیم پاسخ می‌دهم — دربارهٔ محصولات، خدمات، فرایند سفارش، AURION، مقالات یا سیاست‌ها بپرسید.',
      html: 'این سایت در مرحلهٔ توسعه است.'
    },
    en: {
      from: 'From',
      more: 'Read more',
      ask: 'Ask something else',
      unsure: "I couldn't find an approved answer to that. Xiona answers only from what this site publishes — try asking about products, services, the order process, AURION, articles, or the refund policy.",
      nodocs: "I have no knowledge yet. Once a product or article is published, Xiona reads it and can answer from it.",
      greeting: "Hi, I'm Xiona — this site's own assistant. I learn from what AXIASOFT publishes and answer directly. Ask me about products, services, the order process, AURION, articles, or the policies.",
      html: 'This site is in development.'
    }
  };

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
    // A topic this site genuinely does not cover: answer it directly instead of
    // matching a nearby sentence and sounding confident about the wrong thing.
    for (var u = 0; u < UNCOVERED.length; u++) {
      if (UNCOVERED[u][0].test(query)) {
        return { text: UNCOVERED[u][1][language], source: 'policy',
                 language: language, citations: [] };
      }
    }

    var terms = tokenize(query);
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
      var body = focus(hit.doc.text, terms, 340);
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
  Engine.prototype.learnSite = function (options) {
    var opts = options || {};
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
      pages: opts.pages || (Array.isArray(static_.pages) ? static_.pages : [])
    };
    this.learn(args);
    // Footer and header carry the studio's own description on every page.
    if (doc) {
      var footer = doc.querySelector('footer .footer-top > p');
      if (footer) {
        this.add({
          id: 'shell-footer', title: 'AXIASOFT', topic: 'about', route: '#/about',
          text: footer.textContent || ''
        });
      }
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
