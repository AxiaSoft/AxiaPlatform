# Xiona — the support agent

Xiona is the assistant behind the round button in the bottom corner of the
storefront. It is deliberately small: it answers from a curated set of facts
about AXIASOFT, refuses to guess, and never reads account data.

## How it behaves without any setup

With no configuration at all, Xiona answers from `server/agent.py`'s
`KNOWLEDGE` list — ten topics covering products, the order process, timing,
refunds, AURION, services, contact, accounts, privacy and the blog. Retrieval is
keyword overlap with the visitor's question, in English or Persian.

That mode is honest and instant, but the wording is fixed: it assembles the
approved sentences and does not paraphrase.

## Adding a real model

Any OpenAI-compatible endpoint works. Set three environment variables and the
agent starts phrasing its answers with that model, still grounded in the same
facts:

```bash
export AXIA_AGENT_KEY=your-key
export AXIA_AGENT_URL=https://api.groq.com/openai/v1   # provider base URL
export AXIA_AGENT_MODEL=llama-3.3-70b-versatile        # provider model name
```

If the provider is slow, misconfigured or returns an error, the agent falls back
to the local answer automatically — a visitor never sees a stack trace, and the
console reports which mode is active.

## Where to get a free key

| Provider | Free allowance | Base URL | Example model |
|---|---|---|---|
| **Groq** | Generous free tier, very fast | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| **Google AI Studio** | Free tier for Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-2.0-flash` |
| **OpenRouter** | Free models (`:free` suffix) | `https://openrouter.ai/api/v1` | `meta-llama/llama-3.3-70b-instruct:free` |
| **Mistral** | Free "experiment" tier | `https://api.mistral.ai/v1` | `mistral-small-latest` |
| **Cerebras** | Free tier, very fast | `https://api.cerebras.ai/v1` | `llama3.3-70b` |
| **Ollama** (local) | Unlimited, runs on your machine | `http://localhost:11434/v1` | `llama3.2` |

Groq is the easiest starting point: sign in at <https://console.groq.com>, create
an API key, and paste it as `AXIA_AGENT_KEY`.

For a fully offline setup, install [Ollama](https://ollama.com), run
`ollama pull llama3.2`, and set `AXIA_AGENT_URL=http://localhost:11434/v1` with
any non-empty `AXIA_AGENT_KEY` (Ollama ignores the value).

## What it will not do

- It has no database access. Orders, refunds and tickets are session-scoped and
  the agent cannot read or change them.
- It does not invent prices, delivery dates or customer details. Asked something
  outside the facts, it says so and offers a human.
- It does not call the provider with account data — only the visitor's question
  and the recent turns of that conversation, capped at eight.


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
