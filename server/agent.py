"""Xiona — the site's own assistant.

Design decisions, in order of importance:

1. It is self-contained. No API key is required and nothing is sent anywhere:
   ``xiona_engine`` indexes what the site publishes — every published product,
   every article — and answers from that index. The browser runs the same
   engine (``public/xiona.js``) on the static build, so the assistant works
   with no server at all.
2. Nothing is invented. An answer is composed out of sentences the site already
   publishes, with the page it came from attached. When nothing matches, it says
   so rather than filling the gap.
3. It learns from the site, not from a hand-written list. Publishing a product
   or an article teaches it that content; there is no second copy to maintain.
4. It never touches account data. Orders, refunds and tickets are behind the
   session, and the agent has no access to them - it can only create a support
   request on the visitor's behalf, which a person then reads.
5. A model is optional, never required. If AXIA_AGENT_KEY is set, the retrieved
   facts are handed to an OpenAI-compatible endpoint to phrase a nicer answer;
   the retrieval result is still the only source of truth, and a provider
   failure falls back to the local answer.

Environment (all optional):
  AXIA_AGENT_KEY     API key. Unset = local retrieval mode, which is the default.
  AXIA_AGENT_URL     Base URL, default https://api.openai.com/v1
  AXIA_AGENT_MODEL   Model name, default gpt-4o-mini
  AXIA_AGENT_TIMEOUT Seconds before falling back to the local answer, def. 20

Using Google AI Studio (Gemini) instead of OpenAI:

  AXIA_AGENT_KEY=<your AI Studio key>
  AXIA_AGENT_URL=https://generativelanguage.googleapis.com/v1beta/openai
  AXIA_AGENT_MODEL=gemini-2.5-flash

Gemini exposes an OpenAI-compatible surface at that base URL, so nothing else
changes. Any other provider that speaks /chat/completions works the same way.
The model ID is the part that goes stale: `gemini-3.8-flash`, the example this
docstring carried, is not a model Google lists. A 404 from the provider is a
wrong name, not a wrong key - check https://ai.google.dev/gemini-api/docs/models

Check the model name when setting this up. Google retires model IDs on a
published schedule — gemini-2.0-flash, the example this file used to carry,
was shut down on 2026-06-01 and no longer answers. A dead model ID fails the
same way a revoked key does: the site keeps serving the on-site answer and
nothing looks broken. `status()['model_state']` exists to make that visible.

The key is read from the environment on the server only. It is never sent to
the browser, never baked into a built file, and never returned by /api/agent.

Instead of exporting, you can put the same lines in `.env` at the repository
root (copy `.env.example`). That file is git-ignored; a value already in the
environment always wins over it.

Nothing here reads orders, refunds, payments or account details.
"""
import datetime
import json
import os
import re
import urllib.error
import urllib.request

MAX_QUESTION = 800
MAX_HISTORY = 8
# How many turns a saved conversation keeps. The browser trims to the same
# number; this is the server's own bound, because the count arrives from there.
HISTORY_TURNS = 60


def load_env_file(path=None):
    """Read a .env file into os.environ, without overriding real variables.

    The documented setup is three shell exports, which is fine in a terminal
    and awkward everywhere else: a service manager, an IDE run button, a
    `docker compose up` that was given a file. Reading `.env` next to the
    repository root closes that gap, and it is deliberately timid — a value
    already in the environment wins, so an operator who exported a key for one
    run never has it quietly replaced by a stale file.

    Only simple KEY=VALUE lines are understood. No interpolation, no `export`
    prefix, no quoting games: this is a convenience, not a .env parser, and
    anything more clever would be a place for a key to go somewhere unexpected.
    """
    if path is None:
        # Look next to this file's parent (the repository root) and also in the
        # directory the server was started from. The second is what catches the
        # operator who runs `python3 -u server/app.py` from a copy of the site
        # whose `.env` lives beside the folder rather than in it - and Android
        # shared storage, where this site is deployed, is exactly that situation
        # often enough to be worth handling.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [os.path.join(root, '.env'), os.path.join(os.getcwd(), '.env')]
        for candidate in candidates:
            if os.path.isfile(candidate):
                path = candidate
                break
        else:
            path = candidates[0]
    try:
        with open(path, encoding='utf-8') as handle:
            lines = handle.readlines()
    except OSError:
        return {}
    loaded = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key in os.environ:
            continue
        os.environ[key] = value
        loaded[key] = value
    return loaded


# Read once, at import: `status()` and `answer()` both look at os.environ, and
# they must agree about whether a model is configured.
load_env_file()

# The outcome of the last real provider call. "A key is set" is not the same as
# "the model answers": a key can be revoked, the model can be shut down, or the
# host can have no route to the provider at all. Without this the console read
# `provider: model` from the mere presence of a key, so a site whose model had
# never once replied still looked healthy — while every visitor silently got the
# on-site answer instead. `None` means "no call attempted since start".
_LAST_CALL = {'ok': None, 'error': None, 'at': None}

# --------------------------------------------------------------------------- #
# Knowledge
# --------------------------------------------------------------------------- #
# The facts are no longer a hand-written list. They are the site itself: every
# published product and every article, indexed by server/xiona_engine.py — the
# Python twin of the browser engine. Publication is teaching: nothing has to be
# added here when the catalog or the blog grows.

CONTENT_PROVIDERS = None   # set by app.py: (products_fn, articles_fn, stamp_fn)


def configure_content(products_fn, articles_fn, stamp_fn):
    """Tell the agent where the site's content lives.

    app.py owns the database, so it supplies the readers rather than this module
    importing it: the agent stays usable in tests and in the static build, where
    there is no database at all.
    """
    global CONTENT_PROVIDERS
    CONTENT_PROVIDERS = (products_fn, articles_fn, stamp_fn)


def _read_snapshot_list(path, name):
    """Pull one ``window.AXIA_STATIC.<name> = [...]`` literal out of a build file.

    The build writes these as JSON arrays, so they can be read without
    evaluating JavaScript.
    """
    import json
    try:
        with open(path, encoding='utf-8') as handle:
            text = handle.read()
    except OSError:
        return []
    match = re.search(r'window\.AXIA_STATIC\.' + name + r'\s*=\s*(\[.*?\]);',
                      text, re.S)
    if not match:
        return []
    try:
        value = json.loads(match.group(1))
    except ValueError:
        return []
    return [v for v in value if isinstance(v, (dict, list))] if isinstance(value, list) else []


_SNAPSHOT_CACHE = {'key': None, 'pages': []}


def site_pages():
    """Page copy for the index, with the FAQ answers the console edits.

    The FAQ lives in site settings, not on a page function, so a question the
    operator wrote there has to be added explicitly or the assistant cannot
    answer what the site cheerfully displays.
    """
    pages = list(_snapshot()['pages'])
    try:
        settings = _site_settings()
    except Exception:
        settings = {}
    faq = settings.get('faq') if isinstance(settings, dict) else None
    if isinstance(faq, list) and faq:
        lines = []
        for item in faq:
            if not isinstance(item, dict):
                continue
            question = str(item.get('q') or '').strip()
            answer = str(item.get('a') or '').strip()
            if not question or not answer:
                continue
            lines.append(f'Q: {question} A: {answer}')
            # The Persian pair is the same content in the language a Persian
            # visitor asks in; without it, the answer exists but is unreachable.
            question_fa = str(item.get('qFa') or '').strip()
            answer_fa = str(item.get('aFa') or '').strip()
            if question_fa and answer_fa:
                lines.append(f'Q: {question_fa} A: {answer_fa}')
        if lines:
            pages.append({'topic': 'faq', 'route': '#/aurion', 'title': 'Questions',
                          'text': ' '.join(lines), 'language': None,
                          'aliases': 'پرسش سوال پاسخ faq questions answers'})
    return pages


def site_pairs():
    """The site's own Persian/English word list, for crossing languages.

    It ships in its own file — `data/vocabulary.js` — because the browser loads
    it on demand rather than on every page. Reading it from the snapshot found
    nothing, which left a Persian question unable to reach English page copy.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return _read_snapshot_list(os.path.join(root, 'data', 'vocabulary.js'), 'pairs')


def committed_articles():
    """The articles committed to the repository, as a fallback.

    `data/articles.json` is the source of truth for the static build. The server
    reads its articles from the database, which on a fresh checkout is empty
    until someone publishes a post — so an install with two published articles
    in the repository had an assistant that knew about neither. The database
    wins whenever it has anything; this only fills the floor.
    """
    import json
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, 'data', 'articles.json')
    try:
        with open(path, encoding='utf-8') as handle:
            rows = json.load(handle)
    except (OSError, ValueError):
        return []
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not row.get('slug'):
            continue
        item = dict(row)
        item.setdefault('status', 'published')
        if item.get('status') != 'published':
            continue
        out.append(item)
    return out


def _snapshot():
    """The snapshot, re-read only when the file behind it changes."""
    import json
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, 'data', 'products.js')
    try:
        stamp = os.path.getmtime(path), os.path.getsize(path)
    except OSError:
        stamp = None
    if _SNAPSHOT_CACHE['key'] != stamp:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pages = _read_snapshot_list(os.path.join(root, 'data', 'products.js'), 'pages')
        _SNAPSHOT_CACHE.update(key=stamp, pages=pages)
    return _SNAPSHOT_CACHE


def _site_settings():
    """The storefront settings, however this process is configured."""
    global _SETTINGS_PROVIDER
    if _SETTINGS_PROVIDER is None:
        return {}
    return _SETTINGS_PROVIDER() or {}


_SETTINGS_PROVIDER = None


def configure_settings(reader):
    """Let the server hand over its settings document (the FAQ lives there)."""
    global _SETTINGS_PROVIDER
    _SETTINGS_PROVIDER = reader


def engine():
    """The current index, rebuilt only when the content behind it changed.

    The server used to pass products and articles only. That left the assistant
    with no knowledge of the site's own pages, and on a fresh install — where
    the catalog is empty until an administrator adds something, and the blog is
    empty until a post is published — it had no knowledge at all: every question
    came back as "I have no knowledge yet". The static build had already solved
    this by indexing the rendered page copy; the server now does the same, plus
    the FAQ answers the admin console edits and the site's own word list.
    """
    from xiona_engine import get_engine
    if not CONTENT_PROVIDERS:
        return get_engine(lambda: [], lambda: [], ('empty',))
    products_fn, articles_fn, stamp_fn = CONTENT_PROVIDERS

    def articles():
        # The database is authoritative when it has published posts; the
        # committed file fills in for a fresh install that has published none.
        live = list(articles_fn() or [])
        return live if live else committed_articles()

    return get_engine(products_fn, articles, stamp_fn(),
                      pages_provider=_pages_with_assistant,
                      pairs_provider=site_pairs)


# What the assistant says about itself, in the words the panel shows.
#
# The browser engine learns this from the open panel (app.js reads the panel's
# own text and adds it as the 'assistant' chunk). The server has no panel to
# read, so 'شما کی هستید؟' - pronoun and copula only, no content words - found
# no chunk to answer from and replied with whatever retrieval happened to
# match, which was a paragraph about AURION plan durations.
#
# Same sentences, same source of truth: the Persian is what app.js puts in the
# panel for a Persian reader, the English what it puts there otherwise.
ASSISTANT_SELF = {
    'fa': ('Xiona · دستیار همین سایت. همین سایت را یاد می‌گیرد · خودش پاسخ می‌دهد · '
           'بدون سرویس بیرونی. Xiona فقط از آنچه این سایت منتشر کرده پاسخ می‌دهد و '
           'به سفارش‌ها، پرداخت‌ها یا حساب شما دسترسی ندارد.'),
    'en': ('Xiona · on-site assistant. Learns this site · answers on its own · no '
           'outside service. Xiona answers only from what this site publishes. It '
           'cannot see orders, payments or your account.'),
}


def _pages_with_assistant():
    """The site's pages, plus the assistant describing itself."""
    pages = list(site_pages())

    # A clause in each language, so a Persian question is answered from Persian
    # text and an English one from English text.
    for position, language in enumerate(('fa', 'en')):
        pages.append({
            'topic': 'assistant',
            'route': '#/contact',
            'title': 'Xiona',
            'text': ASSISTANT_SELF[language],
            'language': language,
            'aliases': ('assistant bot ai robot who xiona دستیار ربات هوش مصنوعی کی ساخت '
                        'کی هستید شما'),
            'position': position,
        })
    return pages


# The prompt is the contract with the model, and it had two faults that showed
# up as bugs a visitor could feel. It said "answer only from the text below",
# which turned every question the site had not already written down into a
# refusal — an assistant that cannot answer "which one should I pick?" is not
# an assistant. And it said "reply in the language of the question" without
# telling the model what that was, which it got right perhaps two times in
# three; the rest of the time a Persian question came back in English.
#
# So: the site text is the source for facts about AXIASOFT, but the model is
# allowed to reason, compare and recommend. The language is stated explicitly
# rather than inferred, because the caller already knows it — xiona_engine
# detects it to score the retrieval, and the same detection is passed here.
# Anything about money, orders, accounts or delivery dates is still off limits:
# the model must never invent those.
SYSTEM_PROMPT = (
    'You are Xiona, the assistant for AXIASOFT, an independent software studio in Nuremberg. '
    'AXIASOFT builds websites, mobile applications and custom software. AURION is its '
    'trading-robot companion concept: a showcase only, with no broker connection, no '
    'execution and nothing for sale.\n\n'

    'HOW TO ANSWER\n'
    '- Be genuinely useful. Talk like a knowledgeable person, not like a search '
    'greeting. A question gets a real answer with reasoning, comparison and a '
    'recommendation where one is honest to give.\n'
    '- You may use general professional knowledge: how websites are built, what makes an '
    'app slow, whether WordPress or custom code suits a small shop, how long such work '
    'usually takes. Visitors are asking for judgement, not for a paragraph copied out '
    'of the page.\n'
    '- The one thing you must not invent is what AXIASOFT itself has done, charges, or '
    'promises. Products, prices, delivery dates, customer names and policies come from '
    'the PUBLISHED text below. If a specific fact about AXIASOFT is not there, say you '
    'do not have that detail and offer what you do know, or point to the contact page. '
    'Never claim access to orders, payments or the visitor\'s account.\n'
    '- Never quote the PUBLISHED text verbatim at length. Absorb it and answer in your '
    'own words. If the text is in the other language, translate the meaning rather than '
    'pasting it.\n'
    '- Length follows the question. A greeting is one line. A "what is this" is two or '
    'three sentences. A comparison or a "help me choose" can be a short paragraph or a '
    'few bullets - use a list when the answer really is a list.\n'
    '- No marketing filler, no preamble like "Great question!", no restating the '
    'question back.\n\n'

    'LANGUAGE\n'
    'Reply in {language}, the language the visitor wrote in. Detect it from their '
    'message, not from the site. If they write Persian, answer in Persian even if the '
    'PUBLISHED text below is English, and translate anything you take from it. If they '
    'write English, answer in English. If they mix the two, follow the language the '
    'question is actually asked in. Write Persian in Persian script, never '
    'transliterated, in the natural register of someone speaking to a person: '
    '\u200c"می\u200cتوانم" not "می توانم". Keep product names (AXIASOFT, AURION) and '
    'technical terms (MetaTrader, API, WordPress) as they are.\n\n'

    'PUBLISHED:\n{context}'
)

LANGUAGE_NAMES = {'fa': 'Persian (فارسی)', 'en': 'English'}


def _provider_configured():
    return bool(os.environ.get('AXIA_AGENT_KEY'))


def ask_provider(question, history=None, context='', language=None):
    """Ask a language model. Returns ``(text, error)``.

    The endpoint is OpenAI-compatible, which is the useful common denominator:
    OpenAI itself, Google Gemini's compatibility layer, Groq, OpenRouter, a
    local Ollama, and anything else that speaks /chat/completions all work by
    changing two environment variables. There is deliberately no per-provider
    code path here — the differences that matter (base URL, model name) are
    already configuration.
    """
    key = os.environ.get('AXIA_AGENT_KEY')
    base = (os.environ.get('AXIA_AGENT_URL') or 'https://api.openai.com/v1').rstrip('/')
    model = os.environ.get('AXIA_AGENT_MODEL') or 'gpt-4o-mini'
    timeout = float(os.environ.get('AXIA_AGENT_TIMEOUT') or 20)
    # The caller knows the language from the same detection that scored the
    # retrieval, so it is stated rather than left for the model to infer.
    if language not in LANGUAGE_NAMES:
        language = 'fa' if _looks_persian(question) else 'en'
    system = SYSTEM_PROMPT.format(language=LANGUAGE_NAMES[language],
                                  context=(context or '(nothing matched)'))
    messages = [{'role': 'system', 'content': system}]
    for turn in (history or [])[-MAX_HISTORY:]:
        role = 'user' if turn.get('role') == 'user' else 'assistant'
        content = str(turn.get('text') or '')[:MAX_QUESTION]
        if content:
            messages.append({'role': role, 'content': content})
    messages.append({'role': 'user', 'content': question})

    # 400 tokens was a paragraph at most, which is why a question that deserved
    # a comparison got a clipped sentence. The prompt now asks the model to let
    # a greeting be one line and a "help me choose" be a real answer, so the cap
    # has to leave room for the second kind.
    body = json.dumps({'model': model, 'messages': messages, 'temperature': 0.6,
                       'max_tokens': 800}).encode('utf-8')
    request = urllib.request.Request(
        base + '/chat/completions', data=body, method='POST',
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode('utf-8'))
        choice = (payload.get('choices') or [{}])[0]
        text = (choice.get('message') or {}).get('content', '')
        text = (text or '').strip()
        if not text:
            return None, _record_failure('empty response')
        _record_success()
        return text, None
    except urllib.error.HTTPError as exc:
        # The status is the only part that is safe to log: a provider body can
        # echo the key or the prompt back, and this error string is served to
        # the browser.
        return None, _record_failure(f'provider returned {exc.code}')
    except Exception as exc:  # network, DNS, timeout, bad JSON
        return None, _record_failure(type(exc).__name__)


def _record_success():
    _LAST_CALL.update(ok=True, error=None, at=_now())


def _record_failure(reason):
    """Remember the last failure and hand the reason back to the caller."""
    _LAST_CALL.update(ok=False, error=reason, at=_now())
    return reason


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _looks_persian(text):
    """True when the text contains Persian letters.

    A copy of the test in xiona_engine, kept here so this module can decide a
    language without importing the whole index — ask_provider is also used by
    the blog translator, which has no index at all.
    """
    return bool(re.search(r'[\u0600-\u06FF]', str(text or '')))


def answer(question, history=None, language=None):
    """Public entry point. Always returns an answer and how it was produced.

    Retrieval still runs first, because it is what supplies the model with the
    facts it is allowed to state and with the citations the UI shows. But the
    model is no longer skipped when retrieval finds nothing: a question the
    site never wrote down ("which product suits a small shop?") used to be
    answered with "I do not have an approved answer" *without the model ever
    being asked*, which is the exact failure this fixes. Now the model is asked
    whenever one is configured; retrieval only decides how much context it gets.

    With no key configured the local engine is the whole assistant, which is
    the behaviour of the static build and of a fresh checkout.
    """
    question = str(question or '').strip()[:MAX_QUESTION]
    index = engine()
    # The question's language, not the interface's.
    #
    # This was the other way round, and the reversal is deliberate. The old rule
    # - answer in the language the visitor is *reading the site* in - was meant
    # to stop a Persian paragraph on the English build from being quoted at an
    # English reader. In practice it produced the opposite complaint, from the
    # operator: speak Persian to it and it answers in English, because the site
    # happened to be open in English. A person types in the language they want
    # to be answered in; that is the strongest signal there is, and it is right
    # there in the request.
    #
    # `language` from the caller still wins when a caller knows better, but the
    # browser no longer sends one, so this is what decides.
    if language not in LANGUAGE_NAMES:
        language = 'fa' if _looks_persian(question) else 'en'
    local = index.answer(question, language=language)

    # `topics` stays part of the response shape: it names the pages an answer
    # drew on, which the console surfaces and the browser logs.
    local['topics'] = [c['topic'] for c in local.get('citations') or []]
    if not _provider_configured():
        local['provider'] = 'on-site'
        return local

    # Context is built from the retrieval result when there is one, and from a
    # whole-site summary when there is not. Handing the model nothing at all
    # would let it invent AXIASOFT facts; handing it the summary keeps every
    # claim about the studio grounded while still letting it answer the
    # question that retrieval missed.
    if local.get('citations'):
        context = '\n'.join(f"- {c['title']}: {local['answer']}" for c in local['citations'])
    else:
        context = index.summary() or '(nothing matched)'

    text, error = ask_provider(question, history, context, language=local.get('language'))
    if text:
        return {'answer': text, 'source': 'model', 'language': local['language'],
                'citations': local.get('citations') or [], 'provider': 'model'}
    # A provider failure must not look like a refusal: the local answer stands,
    # and `detail` names the reason so an operator can see it in the console.
    local['detail'] = error
    local['provider'] = 'on-site'
    return local


def status():
    """What the console shows about the assistant."""
    # `engine()` builds the index, which reads the database through the
    # providers app.py installs. Everything this function actually reports -
    # provider, model, the last call - comes from the environment and from
    # _LAST_CALL, so a caller asking "is the model wired up?" should not fail
    # because there is no database to build an index from (a test, a fresh
    # checkout, the blog translator). The counts are reported when the index is
    # available and omitted when it is not.
    try:
        state = engine().stats()
    except Exception:
        state = {'chunks': 0, 'topics': [], 'fa': 0, 'en': 0}
    return {
        # 'local' is the historical name for "no provider, answers on-site";
        # the assistant is always local now, so it is always true.
        # A model is a real mode now, not a coat of paint on retrieval, so the
        # console should be able to tell whether it is on.
        'provider': 'model' if _provider_configured() else 'local',
        'engine': 'model+on-site' if _provider_configured() else 'on-site',
        'configured': True,
        'model': (os.environ.get('AXIA_AGENT_MODEL') or 'gpt-4o-mini') if _provider_configured() else None,
        'model_base': (os.environ.get('AXIA_AGENT_URL') or 'https://api.openai.com/v1').rstrip('/') if _provider_configured() else None,
        # Three states an operator needs to tell apart, because they need
        # different fixes: no key (nothing to do), a key that has never been
        # tried (check it once), and a key whose last call failed (the key, the
        # model name, or the network is wrong). The console used to show only
        # the first of those.
        'model_state': (
            'unconfigured' if not _provider_configured()
            else 'untested' if _LAST_CALL['ok'] is None
            else 'ok' if _LAST_CALL['ok']
            else 'failing'
        ),
        'model_last_error': _LAST_CALL['error'] if _provider_configured() else None,
        'model_last_call': _LAST_CALL['at'] if _provider_configured() else None,
        'chunks': state['chunks'],
        # The console counts topics; with a live index the count is the number of
        # distinct sections it learned, which is more useful than a fixed 10.
        'topics': len(state['topics']) or state['chunks'],
        'topics_detail': state['topics'],
        'languages': {'fa': state['fa'], 'en': state['en']},
    }


# --------------------------------------------------------------------------- #
# Article translation
# --------------------------------------------------------------------------- #
# A published post is written once, in whichever language the editor used. The
# English mirror (/en/blog/) needs the same post in English. When a provider is
# configured the text is translated once and stored; when none is configured the
# page is still served, honestly labelled, rather than silently showing Persian
# under an English heading.

TRANSLATE_PROMPT = (
    "You translate website articles into {target}. Rules: preserve Markdown "
    "syntax exactly (headings, lists, emphasis, code fences, link targets); do "
    "not add or remove sentences; keep proper nouns, product names and code "
    "identifiers unchanged; emit only the translation, with no preamble."
)


def translation_available():
    """True when an article can actually be translated right now."""
    return _provider_configured()


def translate(text, target='English'):
    """Translate one block of Markdown. Returns (text, error)."""
    text = str(text or '')
    if not text.strip():
        return '', None
    key = os.environ.get('AXIA_AGENT_KEY')
    if not key:
        # Never invent a translation: without a provider the caller is told so
        # and can label the page instead.
        return None, 'no provider configured'
    base = (os.environ.get('AXIA_AGENT_URL') or 'https://api.openai.com/v1').rstrip('/')
    model = os.environ.get('AXIA_AGENT_MODEL') or 'gpt-4o-mini'
    timeout = float(os.environ.get('AXIA_AGENT_TIMEOUT') or 20)
    body = json.dumps({
        'model': model,
        'messages': [
            {'role': 'system', 'content': TRANSLATE_PROMPT.format(target=target)},
            {'role': 'user', 'content': text[:12000]},
        ],
        'temperature': 0.1,
        'max_tokens': 3000,
    }).encode('utf-8')
    request = urllib.request.Request(
        base + '/chat/completions', data=body, method='POST',
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode('utf-8'))
        out = (payload.get('choices') or [{}])[0].get('message', {}).get('content', '')
        out = (out or '').strip()
        if not out:
            return None, 'empty response'
        # A model that answers with a preamble would break the Markdown pass.
        if out.startswith('```') and out.endswith('```') and '\n' in out:
            out = out.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        return out, None
    except urllib.error.HTTPError as exc:
        return None, f'provider returned {exc.code}'
    except Exception as exc:
        return None, type(exc).__name__


def status_with_translation():
    """Agent status, including whether article translation is possible."""
    state = status()
    state['translation'] = translation_available()
    return state
