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
  AXIA_AGENT_TIMEOUT Seconds before falling back to the local answer, def. 12

Nothing here reads orders, refunds, payments or account details.
"""
import json
import os
import re
import urllib.error
import urllib.request

MAX_QUESTION = 800
MAX_HISTORY = 8

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


def engine():
    """The current index, rebuilt only when the content behind it changed."""
    from xiona_engine import get_engine
    if not CONTENT_PROVIDERS:
        return get_engine(lambda: [], lambda: [], ('empty',))
    products_fn, articles_fn, stamp_fn = CONTENT_PROVIDERS
    return get_engine(products_fn, articles_fn, stamp_fn())


SYSTEM_PROMPT = (
    'You are Xiona, the assistant for AXIASOFT, a small software studio in Nuremberg. '
    'The text below is what this site actually publishes. Answer only from it: do not add '
    'prices, dates, customer names or account details, and never claim access to orders or '
    'payments. If the text does not cover the question, say you do not have an approved '
    'answer and offer a human. Reply in the language of the question, in at most four '
    'sentences, plainly and without marketing filler.\n\nPUBLISHED:\n'
)


def _provider_configured():
    return bool(os.environ.get('AXIA_AGENT_KEY'))


def ask_provider(question, history=None, context=''):
    """Ask an OpenAI-compatible endpoint. Returns (text, error)."""
    key = os.environ.get('AXIA_AGENT_KEY')
    base = (os.environ.get('AXIA_AGENT_URL') or 'https://api.openai.com/v1').rstrip('/')
    model = os.environ.get('AXIA_AGENT_MODEL') or 'gpt-4o-mini'
    timeout = float(os.environ.get('AXIA_AGENT_TIMEOUT') or 12)
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT + (context or '(nothing matched)')}]
    for turn in (history or [])[-MAX_HISTORY:]:
        role = 'user' if turn.get('role') == 'user' else 'assistant'
        content = str(turn.get('text') or '')[:MAX_QUESTION]
        if content:
            messages.append({'role': role, 'content': content})
    messages.append({'role': 'user', 'content': question})

    body = json.dumps({'model': model, 'messages': messages, 'temperature': 0.2,
                       'max_tokens': 260}).encode('utf-8')
    request = urllib.request.Request(
        base + '/chat/completions', data=body, method='POST',
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode('utf-8'))
        text = (payload.get('choices') or [{}])[0].get('message', {}).get('content', '')
        text = (text or '').strip()
        return (text, None) if text else (None, 'empty response')
    except urllib.error.HTTPError as exc:
        return None, f'provider returned {exc.code}'
    except Exception as exc:  # network, DNS, timeout, bad JSON
        return None, type(exc).__name__


def answer(question, history=None):
    """Public entry point. Always returns an answer and how it was produced.

    The local engine answers first. That is not a fallback path any more: it is
    the assistant. A configured model may rephrase the retrieved material, but
    it never sees a question the site cannot answer and never adds a fact.
    """
    question = str(question or '').strip()[:MAX_QUESTION]
    index = engine()
    local = index.answer(question)

    # `topics` stays part of the response shape: it names the pages an answer
    # drew on, which the console surfaces and the browser logs.
    local['topics'] = [c['topic'] for c in local.get('citations') or []]
    if not _provider_configured() or local['source'] in ('empty', 'empty-index', 'no-match'):
        local['provider'] = 'on-site'
        return local

    context = '\n'.join(f"- {c['title']}: {local['answer']}" for c in local.get('citations') or [])
    text, error = ask_provider(question, history, context)
    if text:
        return {'answer': text, 'source': 'model', 'language': local['language'],
                'citations': local.get('citations') or [], 'provider': 'model'}
    # A provider failure must not look like a refusal: the local answer stands.
    local['detail'] = error
    local['provider'] = 'on-site'
    return local


def status():
    """What the console shows about the assistant."""
    index = engine()
    state = index.stats()
    return {
        # 'local' is the historical name for "no provider, answers on-site";
        # the assistant is always local now, so it is always true.
        'provider': 'local',
        'engine': 'on-site',
        'configured': True,
        'model': os.environ.get('AXIA_AGENT_MODEL') if _provider_configured() else None,
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
