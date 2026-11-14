#!/usr/bin/env python3
"""Write data/translations.json — the English copy of the Persian blog.

The static site publishes `/blog/` in the language each article was written in
and `/en/blog/` as its English mirror. The mirror needs the article text in
English, and the build cannot produce that by itself: it reads whatever is
already in `data/translations.json` and, for a post with no entry, renders the
original with a notice rather than pretending a translation exists.

This tool fills that file. It talks to the same OpenAI-compatible endpoint the
console's assistant uses (AXIA_AGENT_KEY, AXIA_AGENT_URL, AXIA_AGENT_MODEL) and
is meant to be run by a person, once, before a build:

    export AXIA_AGENT_KEY=...
    python3 tools/translate_articles.py            # translate what is missing
    python3 tools/translate_articles.py --force    # re-translate everything
    python3 tools/translate_articles.py --check    # exit 1 if anything is owed

Each entry is keyed by slug and carries a `source_hash`, the same digest the
console stores. Running it after editing a post re-translates only that post, and
a post already translated is never paid for twice.

Without a provider the tool says so and exits 2. It never writes a guessed or
machine-free translation: half-English copy under an English heading is worse
than an honest notice.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'server'))

ARTICLES = ROOT / 'data' / 'articles.json'
OUTPUT = ROOT / 'data' / 'translations.json'

# The three fields the blog renders. A post is owed a translation when the
# source text behind any of them has changed, which is what the hash covers.
FIELDS = ('title', 'summary', 'body')


def digest(article: dict) -> str:
    """The same hash server/blog.py uses, so both agree on what is stale."""
    source = '\n\x00\n'.join(str(article.get(field) or '') for field in FIELDS)
    return hashlib.sha256(source.encode('utf-8')).hexdigest()[:32]


def load(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8')) or {}
    except (OSError, ValueError):
        return {}


def target_language(article: dict) -> str:
    """Which language the mirror needs for this article.

    The blog is Persian-first, so the mirror is English. An article written in
    English already is its own mirror and needs no call.
    """
    return 'fa' if str(article.get('language') or 'fa') == 'en' else ''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--force', action='store_true', help='re-translate posts that are already current')
    parser.add_argument('--check', action='store_true', help='report what is owed and exit; write nothing')
    parser.add_argument('--source', default=str(ARTICLES), help='articles JSON to read')
    parser.add_argument('--output', default=str(OUTPUT), help='translations JSON to write')
    options = parser.parse_args()

    source_path, output_path = Path(options.source), Path(options.output)
    articles = load(source_path)
    if isinstance(articles, dict):
        articles = articles.get('articles', [])
    if not articles:
        print(f'no articles in {source_path}', file=sys.stderr)
        return 0

    stored = load(output_path)
    owed = []
    for article in articles:
        slug = str(article.get('slug') or '').strip()
        if not slug:
            continue
        # An article written in English needs no English mirror.
        if str(article.get('language') or 'fa') == 'en':
            continue
        current = stored.get(slug) or {}
        if options.force or current.get('source_hash') != digest(article):
            owed.append(article)

    if not owed:
        print(f'all {len(articles)} article(s) are translated')
        return 0

    print(f'{len(owed)} of {len(articles)} article(s) need English copy:')
    for article in owed:
        print(f"  · {article.get('slug')}")
    if options.check:
        return 1

    try:
        import agent
    except Exception as exc:  # noqa: BLE001 - report, do not crash the build
        print(f'could not import the translation client: {exc}', file=sys.stderr)
        return 2
    if not agent.translation_available():
        print('\nNo provider is configured, so nothing was written.\n'
              'Set AXIA_AGENT_KEY (and AXIA_AGENT_URL / AXIA_AGENT_MODEL if the\n'
              'endpoint is not OpenAI). Until then /en/blog/ shows each post in\n'
              'its original language with a notice saying so.', file=sys.stderr)
        return 2

    written = 0
    for article in owed:
        slug = str(article.get('slug'))
        target = target_language(article) or 'English'
        translated, failed = {}, None
        for field in FIELDS:
            text = str(article.get(field) or '')
            if not text.strip():
                translated[field] = ''
                continue
            out, error = agent.translate(text, target=target)
            if out is None:
                failed = error or 'the provider returned nothing'
                break
            translated[field] = out
        if failed:
            print(f'  ✕ {slug}: {failed}', file=sys.stderr)
            continue
        entry = dict(translated)
        entry['source_hash'] = digest(article)
        entry['translated_at'] = _now()
        stored[slug] = entry
        written += 1
        print(f'  ✓ {slug}')

    if written:
        # Written one key at a time in a stable order so a diff shows exactly
        # which post changed rather than the whole file moving.
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ordered = {slug: stored[slug] for slug in sorted(stored)}
        output_path.write_text(json.dumps(ordered, ensure_ascii=False, indent=1) + '\n',
                               encoding='utf-8')
        print(f'\nwrote {written} translation(s) to {output_path}')
    return 0 if written == len(owed) else 1


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


if __name__ == '__main__':
    raise SystemExit(main())
