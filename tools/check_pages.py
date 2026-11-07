#!/usr/bin/env python3
"""Check what GitHub Pages is actually serving for this repository.

Two different things decide whether the site loads:

  1. the *content* on the branch Pages points at (does its root have an
     index.html, and is .nojekyll there so Jekyll does not turn README.md into
     the homepage?), and
  2. the *Pages setting* (which branch and folder Pages was told to serve).

A repository can be perfectly correct and still show the README, and it can also
be misconfigured while the content is fine. This script separates the two.

Usage:
    python3 tools/check_pages.py              # introspect with the GitHub CLI
    python3 tools/check_pages.py --repo owner/name
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

FILES = ('index.html', '404.html', '.nojekyll', 'styles.css', 'app.js',
         'static-adapter.js', 'style.css', 'data/products.json')


def gh(*args: str) -> tuple[bool, str]:
    try:
        out = subprocess.run(('gh',) + args, capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return out.returncode == 0, (out.stdout or out.stderr).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description='Diagnose the GitHub Pages setup')
    parser.add_argument('--repo', default='AxiaSoft/AxiaPlatform')
    parser.add_argument('--branch', default='main')
    args = parser.parse_args()

    print(f'Repository : {args.repo}')
    problems: list[str] = []

    # --- what the branch contains -----------------------------------------
    ok, listing = gh('api', f'repos/{args.repo}/contents/?ref={args.branch}',
                     '--jq', '.[].name')
    if not ok:
        print(f'\n! Could not read the {args.branch} tree:\n  {listing}')
        return 2
    names = set(listing.split())
    print(f'Branch     : {args.branch}')

    has_index = 'index.html' in names
    has_nojekyll = '.nojekyll' in names
    print(f'  index.html : {"yes" if has_index else "NO  <-- Pages shows README.md instead"}')
    print(f'  .nojekyll  : {"yes" if has_nojekyll else "NO  <-- Jekyll renders README.md as the homepage"}')
    if not has_index:
        problems.append(f'{args.branch} root has no index.html, so Pages falls back to README.md.')
    if not has_nojekyll:
        problems.append(f'{args.branch} root has no .nojekyll, so Jekyll may render README.md as the homepage.')

    # --- what Pages is configured to serve --------------------------------
    ok, pages = gh('api', f'repos/{args.repo}/pages')
    if not ok:
        print(f'\n  Pages API : unavailable ({pages.splitlines()[0] if pages else "no access"})')
        problems.append('Could not read the Pages configuration (needs admin). Check it in the UI.')
    else:
        data = json.loads(pages)
        source = data.get('source') or {}
        branch = source.get('branch', '?')
        path = source.get('path', '?')
        print(f'\nPages says : branch={branch}  path={path}  status={data.get("status")}')
        print(f'             url={data.get("html_url")}')
        if branch != args.branch:
            problems.append(
                f'Pages serves branch "{branch}" but the site was published to "{args.branch}". '
                f'In Settings -> Pages set the source to {args.branch} / (root).')
        if path not in ('/', '/docs'):
            problems.append(f'Pages serves the folder "{path}", which is not where the site was built.')

    # --- verdict ----------------------------------------------------------
    print()
    if problems:
        print('Problems found:')
        for index, item in enumerate(problems, 1):
            print(f'  {index}. {item}')
        print('\nFix it in the browser (no token needed):')
        print(f'  Settings -> Pages -> Build and deployment')
        print(f'  Source: Deploy from a branch -> Branch: {args.branch} -> Folder: / (root) -> Save')
        print('Or, for a workflow build, choose Source: GitHub Actions and add')
        print('  tools/pages-workflow.yml as .github/workflows/pages.yml')
        return 1

    print('The setup looks correct. If the browser still shows the README, it is a')
    print('cached copy: hard-reload (Ctrl/Cmd+Shift+R) or open the URL in a private window.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
