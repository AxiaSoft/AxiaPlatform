# Xiona — the support agent

Xiona is the assistant behind the round button in the bottom corner of the
storefront. It is deliberately small: it answers from a curated set of facts
about AXIASOFT, refuses to guess, and never reads account data.

## How it behaves without any setup

With no configuration at all, Xiona answers from `server/agent.py`'s
`KNOWLEDGE` list — ten topics covering products, the order process, timing,
refunds, AURION, services, contact, accounts, privacy and the blog. Retrieval is
keyword overlap with the visitor's question, in English or Persian.

That mode is honest and instant, but it is retrieval, not intelligence: the
wording is fixed, it assembles the approved sentences rather than paraphrasing
them, and a question the site has not written down gets an "I do not have an
approved answer" reply. **To get a real assistant, configure a model — see
below.** Without one, Xiona is a search box that speaks in sentences, and it
will feel like one.

## Adding a real model

Any OpenAI-compatible endpoint works. Set three environment variables and the
agent starts answering with that model:

```bash
export AXIA_AGENT_KEY=your-key
export AXIA_AGENT_URL=https://generativelanguage.googleapis.com/v1beta/openai
export AXIA_AGENT_MODEL=gemini-2.0-flash
```

The model is what makes Xiona an assistant rather than a search box:

- It answers questions the site never wrote down, and it may reason, compare and
  recommend. Facts about AXIASOFT still come from the site's published text,
  which is handed to it as context; it is told never to invent a price, a
  delivery date or an account detail.
- It replies in the visitor's language. The language is detected on the server
  from the same pass that scores the retrieval, and passed to the model
  explicitly rather than left to be guessed.

If the provider is slow, misconfigured or returns an error, the agent falls back
to the retrieved answer automatically — a visitor never sees a stack trace, and
the console reports which mode is active (`/api/agent` returns
`provider: "model"` when a model answered).

## Where to get a free key

| Provider | Free allowance | Base URL | Example model |
|---|---|---|---|
| **Groq** | Generous free tier, very fast | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| **Google AI Studio** ⭐ | Free tier for Gemini, best Persian | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-2.0-flash` |
| **OpenRouter** | Free models (`:free` suffix) | `https://openrouter.ai/api/v1` | `meta-llama/llama-3.3-70b-instruct:free` |
| **Mistral** | Free "experiment" tier | `https://api.mistral.ai/v1` | `mistral-small-latest` |
| **Cerebras** | Free tier, very fast | `https://api.cerebras.ai/v1` | `llama3.3-70b` |
| **Ollama** (local) | Unlimited, runs on your machine | `http://localhost:11434/v1` | `llama3.2` |

**Google AI Studio is the recommended starting point**, especially for a Persian
site: sign in at <https://aistudio.google.com/apikey>, create a key, and use the
three variables above. Its free tier is enough for a brochure site, and its
Persian is noticeably better than the free Groq models.

Groq is a good alternative if you want speed: sign in at
<https://console.groq.com>, create an API key, and set
`AXIA_AGENT_URL=https://api.groq.com/openai/v1` with a Llama model.

The key is read from the environment on the server. It is never sent to the
browser, never written into a built file, and never returned by `/api/agent`.

For a fully offline setup, install [Ollama](https://ollama.com), run
`ollama pull llama3.2`, and set `AXIA_AGENT_URL=http://localhost:11434/v1` with
any non-empty `AXIA_AGENT_KEY` (Ollama ignores the value).

## What it will not do

- It has no database access. Orders, refunds and tickets are session-scoped and
  the agent cannot read or change them.
- It does not invent prices, delivery dates or customer details. With no model
  configured it says so plainly; with one configured, the model is told the same
  rule and the site text it is given is the only source for studio facts.
- It does not call the provider with account data — only the visitor's question
  and the recent turns of that conversation, capped at eight.


## Language

Xiona answers in **the language the site is being read in**, not the language
the question happens to be typed in. A visitor on the Persian site who types
English gets a Persian answer; a visitor on the English site who types Persian
gets an English one.

This is not a convenience. It was a bug with two causes:

1. `answer()` took no language argument, so the reply language was inferred from
   the question. Persian in, Persian out — but on the *English* site, which is
   not what the visitor asked for.
2. Retrieval searched the whole corpus regardless of language. The English build
   indexes roughly 21 English chunks against 3 Persian ones, because the page
   copy is written once and translated by `i18n.js` in the browser. The
   best-scoring hit was therefore almost always English, and its text was quoted
   back at a Persian reader — "I spoke Persian and it answered in English".

The interface language now travels with the request: `app.js` sends
`{language: 'fa'|'en'}` to `/api/agent`, the route passes it to `agent.answer()`,
and the engine searches its own language first. The prompt states the language
explicitly and tells the model not to mirror the question.

When the site's language genuinely has no text for a question, the answer says
so *in that language* and — if the other language does cover it — mentions that
the site is partly English-only, so the visitor knows why. It never quotes the
other language as the answer.

`uncovered_text()` drops any of the visitor's words that are written in a
different script, so a Persian question on the English site does not produce
`This site does not publish anything about "محصولات"`.

## Conversation history

The chat outlives the panel, and where it is kept depends on who is asking.

**Signed in** — the conversation belongs to the account, in an `agent_history`
row keyed to `user_id`. It comes back on any device, because the session cookie
is what identifies it. The account copy is authoritative: a tab that holds
someone else's history (a shared machine) never shows it, even for a moment.

**Signed out** — there is no identity to attach it to, so it lives in
`sessionStorage`. That is scoped to the tab and is discarded when the browser
session ends, which is the requested behaviour: it survives a reload, a
route change and closing the panel, and dies with the browser. `localStorage`
would have kept one visitor's questions on a shared machine indefinitely.

The endpoints:

| method | path | behaviour |
| --- | --- | --- |
| `GET` | `/api/agent/history` | the account's turns; `401` when signed out |
| `POST` | `/api/agent/history` | replace it, CSRF-checked, capped at 60 turns |
| `DELETE` | `/api/agent/history` | forget it |

The `401` is load-bearing: the browser reads it as "keep this in the tab
instead", which is why the static build (where every write is unavailable) and
a signed-out visitor take the same path rather than an error path.

Writes are cleaned server-side — unknown roles become `bot`, blanks and
non-objects are dropped, and each turn is truncated to `MAX_QUESTION` — because
the list arrives from the browser.

## Translating the articles

The blog is written once, in whichever language the editor used. `/en/blog/` is
the same articles with an English interface, and each article is translated on
demand:

1. The first request for `/en/blog/<slug>/` sends the title, summary and body to
   the provider configured by the same three environment variables above.
2. The result is stored in `article_translations`, keyed to a hash of the source
   text. Editing the post changes the hash, so the next request re-translates.
3. If no provider is configured the page is still served. It keeps the original
   text in its own direction and shows a notice saying the article has not been
   translated yet — it never presents untranslated text as English.

For the static GitHub Pages build, translations come from
`data/translations.json` (keyed by slug). Without it, `/en/blog/<slug>/` is
built with the notice in place, so no link dead-ends.

A translation is one model call per field. With a free tier that is ample for a
blog that publishes a few posts a week, and the cache means a post is only paid
for once.
