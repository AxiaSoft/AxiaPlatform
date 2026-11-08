"""Xiona — the site's support agent.

Design decisions, in order of importance:

1. It answers from this site, not from the open internet. The knowledge is a
   small, curated fact list; when nothing matches, it says so and offers a
   human. An assistant that invents a price or a delivery date is worse than no
   assistant.
2. It never touches account data. Orders, refunds and tickets are behind the
   session, and the agent has no access to them - it can only create a support
   request on the visitor's behalf, which a person then reads.
3. It is provider-agnostic. If AXIA_AGENT_KEY is set, the question and the site
   knowledge are sent to an OpenAI-compatible /chat/completions endpoint
   (Ollama, Groq, OpenRouter, Together, LM Studio and OpenAI all speak this).
   With no key configured, a local retrieval answerer handles the request, so
   the feature works out of the box and in the static demo.

Environment:
  AXIA_AGENT_KEY     API key. Unset = local retrieval mode.
  AXIA_AGENT_URL     Base URL, default https://api.openai.com/v1
  AXIA_AGENT_MODEL   Model name, default gpt-4o-mini
  AXIA_AGENT_TIMEOUT Seconds before falling back to the local answer, def. 12
"""
import json
import os
import re
import urllib.error
import urllib.request

MAX_QUESTION = 800
MAX_HISTORY = 8

# Everything the agent is allowed to assert. Each fact is a topic, the phrases
# that should retrieve it, and the answer. Retrieval is keyword overlap, which
# is enough for a site this size and keeps the whole feature auditable.
KNOWLEDGE = [
    {
        'id': 'products',
        'keys': ['product', 'products', 'catalog', 'catalogue', 'محصول', 'محصولات', 'کاتالوگ', 'نمونه'],
        'answer': ('The catalog holds a small set of production-ready starting points — brand websites, '
                   'client portals and the AURION showcase. Each one is a scope, not a fixed product: '
                   'we shape it around your goals. Open Products to see what is available right now.'),
    },
    {
        'id': 'order',
        'keys': ['order', 'request', 'start', 'project', 'quote', 'price', 'cost', 'سفارش', 'پروژه',
                 'شروع', 'قیمت', 'هزینه', 'پیش‌فاکتور', 'درخواست'],
        'answer': ('Starting a project takes a minute: open a product, choose "Request this product", and '
                   'share what you are building. You get a reference number immediately and the team reviews '
                   'it. A quotation is agreed separately after that review — this site never takes a payment.'),
    },
    {
        'id': 'aurion',
        'keys': ['aurion', 'metatrader', 'trading', 'license', 'آوریون', 'معاملات', 'لایسنس', 'مجوز'],
        'answer': ('AURION is a concept showcase for software intended to work in the MetaTrader environment. '
                   'It does not connect to a broker, place trades or activate licences, and nothing about it '
                   'is financial advice. Trading carries risk.'),
    },
    {
        'id': 'timing',
        'keys': ['how long', 'timeline', 'deadline', 'when', 'delivery', 'time', 'چقدر', 'زمان', 'مدت',
                 'تحویل', 'چه وقت'],
        'answer': ('Timing follows scope, so I cannot give you a date before the work is understood. '
                   'A sensible sequence is: request, short review call, agreed scope, then a schedule with '
                   'dates. Once scope is agreed the team commits to those dates in writing.'),
    },
    {
        'id': 'refund',
        'keys': ['refund', 'cancel', 'money back', 'policy', 'بازپرداخت', 'لغو', 'استرداد', 'بازگشت'],
        'answer': ('A refund can be requested within 14 calendar days of the applicable purchase date, '
                   'subject to the published terms and applicable law. Requests are reviewed by a person; '
                   'that review does not guarantee approval, and this site does not move money itself.'),
    },
    {
        'id': 'services',
        'keys': ['service', 'services', 'website', 'app', 'application', 'software', 'development', 'کار',
                 'خدمات', 'وب‌سایت', 'سایت', 'اپلیکیشن', 'نرم‌افزار', 'توسعه'],
        'answer': ('There are three ways in: brand-led websites, mobile applications, and custom software for '
                   'specific operations. The approach is the same in each — small steps, something reviewable '
                   'at every stage, and no surprise scope at the end.'),
    },
    {
        'id': 'contact',
        'keys': ['contact', 'email', 'phone', 'talk', 'human', 'person', 'support', 'تماس', 'ایمیل',
                 'تلفن', 'انسان', 'پشتیبان', 'پشتیبانی', 'گفت‌وگو'],
        'answer': ('You can reach a person from Contact, or I can open a support request for you here — '
                   'tell me what is happening and I will pass it on. I cannot promise a response time, and '
                   'I never read or change account records.'),
    },
    {
        'id': 'account',
        'keys': ['account', 'sign in', 'login', 'password', 'status', 'track', 'حساب', 'ورود', 'رمز',
                 'وضعیت', 'پیگیری'],
        'answer': ('Signing in shows your own requests and their latest status. I cannot look up private '
                   'order information myself — for anything account-specific, sign in or ask me for a '
                   'human and I will raise a support request.'),
    },
    {
        'id': 'privacy',
        'keys': ['privacy', 'data', 'gdpr', 'cookie', 'حریم', 'داده', 'کوکی'],
        'answer': ('We collect what is needed to answer an enquiry, run an account and deliver agreed work. '
                   'The Privacy policy sets out what is stored and how to ask for a copy or deletion.'),
    },
    {
        'id': 'blog',
        'keys': ['blog', 'article', 'write', 'post', 'وبلاگ', 'مقاله', 'نوشته', 'مطلب'],
        'answer': ('The blog collects notes on how this kind of work actually goes — performance, structure, '
                   'the decisions behind a product. Every article has its own page at /blog/.'),
    },
]

FALLBACK = ('I do not have an approved answer for that yet. I can help with products, the order process, '
            'timing, refunds, AURION, or reaching a person — and I can open a support request if you '
            'would rather a human replied.')

SYSTEM_PROMPT = (
    'You are Xiona, the support assistant for AXIASOFT, a small software studio in Nuremberg. '
    'Answer only from the facts below. If a question is not covered, say you do not have an approved '
    'answer and offer a human. Never invent prices, delivery dates, customer names or account details. '
    'Never claim access to orders or payments. Reply in the language of the question, in at most four '
    'sentences, plainly and without marketing filler.\n\nFACTS:\n'
)


def _tokens(text):
    return set(re.findall(r'[a-z0-9\u0600-\u06ff]+', (text or '').lower()))


def retrieve(question, limit=2):
    """Score every fact by how many of its trigger phrases appear."""
    lowered = (question or '').lower()
    scored = []
    for fact in KNOWLEDGE:
        score = 0
        for key in fact['keys']:
            if key in lowered:
                score += 2 if ' ' in key else 1
        if score:
            scored.append((score, fact))
    scored.sort(key=lambda pair: -pair[0])
    return [fact for _, fact in scored[:limit]]


def local_answer(question):
    """Deterministic answer from the curated facts (no network, no model)."""
    facts = retrieve(question)
    if not facts:
        return FALLBACK, []
    return ' '.join(f['answer'] for f in facts[:2]), [f['id'] for f in facts]


def _provider_configured():
    return bool(os.environ.get('AXIA_AGENT_KEY'))


def ask_provider(question, history=None):
    """Ask an OpenAI-compatible endpoint. Returns (text, error)."""
    key = os.environ.get('AXIA_AGENT_KEY')
    base = (os.environ.get('AXIA_AGENT_URL') or 'https://api.openai.com/v1').rstrip('/')
    model = os.environ.get('AXIA_AGENT_MODEL') or 'gpt-4o-mini'
    timeout = float(os.environ.get('AXIA_AGENT_TIMEOUT') or 12)
    facts = '\n'.join(f"- {f['id']}: {f['answer']}" for f in KNOWLEDGE)
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT + facts}]
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
    """Public entry point. Always returns an answer and how it was produced."""
    question = str(question or '').strip()[:MAX_QUESTION]
    if not question:
        return {'answer': FALLBACK, 'source': 'local', 'topics': []}
    if _provider_configured():
        text, error = ask_provider(question, history)
        if text:
            return {'answer': text, 'source': 'model', 'topics': [f['id'] for f in retrieve(question)]}
        # A provider failure must not look like a refusal: fall back, and let the
        # client log the reason rather than showing it to the visitor.
        fallback, topics = local_answer(question)
        return {'answer': fallback, 'source': 'local-fallback', 'topics': topics, 'detail': error}
    text, topics = local_answer(question)
    return {'answer': text, 'source': 'local', 'topics': topics}


def status():
    """What the console shows about the agent's configuration."""
    return {
        'provider': 'openai-compatible' if _provider_configured() else 'local',
        'model': os.environ.get('AXIA_AGENT_MODEL') or ('gpt-4o-mini' if _provider_configured() else None),
        'configured': _provider_configured(),
        'topics': len(KNOWLEDGE),
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
