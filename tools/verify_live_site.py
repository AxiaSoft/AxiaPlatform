#!/usr/bin/env python3
"""Tell me exactly what my GitHub Pages URL is showing right now.

The browser is not always a reliable witness: it caches aggressively, and a
misaimed Pages source looks identical to a cached page. This script fetches the
real, current bytes of the site and says which of these is happening:

  * PAGE   — the AXIASOFT site is being served (correct)
  * README — the repository README is being served (Pages is pointed somewhere
             without an index.html, or Jekyll is processing the tree)
  * EMPTY  — nothing useful came back

Unlike the deployment checks this runs from your machine against the public
URL, so it needs nothing but Python's standard library.

Usage:
    python3 tools/verify_live_site.py
    python3 tools/verify_live_site.py --url https://example.com/path/
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request

DEFAULT_URL = 'https://axiasoft.github.io/AxiaPlatform/'

# Marker that only the real storefront has.
SITE_MARKERS = ('AXIASOFT', 'Building What', 'static-adapter.js', 'styles.css')
README_MARKERS = ('<h1', 'AxiaPlatform', '```', '<details', 'github.com/AxiaSoft')


def fetch(url: str, timeout: int = 30) -> tuple[int, str, dict]:
    request = urllib.request.Request(url, headers={
        'User-Agent': 'axiasoft-pages-check/1.0',
        'Cache-Control': 'no-cache',
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode('utf-8', 'replace')
        return response.status, body, dict(response.headers)


def main() -> int:
    parser = argparse.ArgumentParser(description='Check what the live Pages URL serves')
    parser.add_argument('--url', default=DEFAULT_URL)
    args = parser.parse_args()

    print(f'Fetching {args.url}\n')

    try:
        status, body, headers = fetch(args.url)
    except urllib.error.HTTPError as exc:
        print(f'  HTTP {exc.code} {exc.reason}')
        return 2
    except urllib.error.URLError as exc:
        print(f'  Could not reach the host: {exc.reason}')
        print('\n  If your browser can open it but this cannot, a proxy or DNS is')
        print('  blocking the sandbox - check in a private window instead.')
        return 2
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        print(f'  Request failed: {exc}')
        return 2

    size = len(body)
    print(f'  HTTP {status}   {size:,} bytes   server={headers.get("Server", "?")}')
    print(f'  x-origin-cache={headers.get("X-Origin-Cache", "-")}')

    # What kind of document is this?
    title = re.search(r'<title>(.*?)</title>', body, re.S | re.I)
    title = title.group(1).strip() if title else '(no title)'
    is_site = ('static-adapter.js' in body and 'styles.css' in body) or '<div id="app"' in body
    is_readme = (not is_site) and (body.count('\n# ') > 3 or 'AxiaPlatform' in title or
                                   any(marker in body for marker in README_MARKERS))

    print(f'\n  <title> {title}')

    print('\n  Verdict:', end=' ')
    if is_site:
        print('PAGE - the AXIASOFT site is live.')
        print('\n  Assets:')
        for match in sorted(set(re.findall(r'(?:href|src)="(/[^"]+\.(?:css|js|png|woff2)[^"]*)"', body))):
            path = match.split('?')[0]
            absolute = args.url.split('/AxiaPlatform')[0] + path if path.startswith('/AxiaPlatform') else None
            if not absolute:
                print(f'    ?  {path}')
                continue
            try:
                with urllib.request.urlopen(absolute, timeout=15) as asset:
                    print(f'    {asset.status}  {path}')
            except Exception:  # noqa: BLE001
                print(f'    ERR {path}')
        return 0

    if is_readme:
        print('README - Pages is serving the repository README, not the site.')
        print('\n  The usual cause: Pages is pointed at a branch or folder whose root has')
        print('  no index.html, or .nojekyll is missing so Jekyll renders README.md.')
        print('\n  Fix, in the browser:')
        print('    Settings -> Pages -> Build and deployment')
        print('    Source: Deploy from a branch -> Branch: main -> Folder: / (root) -> Save')
        print('\n  Then check where it is aimed:  python3 tools/check_pages.py')
        return 1

    print('UNKNOWN - neither the site nor the README.')
    print('\n  First 300 characters of what came back:\n')
    print('  ' + body[:300].replace('\n', '\n  '))
    return 1


if __name__ == '__main__':
    sys.exit(main())
