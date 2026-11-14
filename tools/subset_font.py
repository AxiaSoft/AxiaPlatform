#!/usr/bin/env python3
"""Rebuild the Persian webfont as a subset of the characters the site can show.

The shipped Vazirmatn variable font is 111 KB and carries every Arabic-script
glyph the upstream project supports. This site can only render the characters
that appear in its own strings, so the rest is downloaded by every visitor and
never drawn. Subsetting takes it to ~66 KB (-40%) with no visible change: the
same text renders to the same pixels at the same metrics.

Run it after adding content in a script the font is not yet covering:

    pip install fonttools brotli
    python3 tools/subset_font.py

It rewrites public/fonts/Vazirmatn-Variable.woff2 in place and prints the before
and after sizes. The character set is derived from the source files, never from
a hand-written list, so it tracks the site instead of drifting behind it.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / 'public' / 'fonts' / 'Vazirmatn-Variable.woff2'
# The untouched upstream font lives outside public/ on purpose: nothing links to
# it, and a 111 KB file sitting in the published tree is one build-config slip
# away from being served to every visitor. A test checks it never is.
ORIGINAL = ROOT / 'tools' / 'assets' / 'Vazirmatn-Variable.full.woff2'

# Every file whose text can reach the screen in a script this font serves. The
# catalog snapshots are included because an operator's product title is rendered
# with whatever characters they typed.
SOURCES = [
    'public/i18n.js', 'public/app.js', 'public/brands.js', 'public/xiona.js',
    'public/admin/admin.js', 'data/products.js', 'data/settings.js',
]

# Marks that never appear literally in source but are composed when Persian is
# shaped: harakat, superscript alef, the Quranic annotation range, and the
# presentation forms a shaper may pick for a ligature.
ALWAYS = [(0x064B, 0x065F), (0x0670, 0x0670), (0x06D6, 0x06ED),
          (0xFB50, 0xFDFF), (0xFE70, 0xFEFF), (0x2000, 0x206F)]
EXTRA = (0x2190, 0x2192, 0x2191, 0x2193, 0x2713, 0x25C8, 0x2726)


def main() -> int:
    try:
        from fontTools.ttLib import TTFont
        from fontTools.subset import Subsetter, Options
    except ImportError:
        print('fontTools is not installed: pip install fonttools brotli', file=sys.stderr)
        return 1

    if not ORIGINAL.exists():
        # Keep an untouched copy the first time so the subset is always derived
        # from the full font, not from a previous subset.
        ORIGINAL.write_bytes(TARGET.read_bytes())
        print(f'  saved the full font to {ORIGINAL.relative_to(ROOT)}')

    before = ORIGINAL.stat().st_size
    font = TTFont(str(ORIGINAL))
    cmap = font.getBestCmap()

    chars = set()
    for name in SOURCES:
        path = ROOT / name
        if path.exists():
            chars.update(path.read_text(encoding='utf-8'))

    wanted = {cp for cp in cmap if chr(cp) in chars}
    for lo, hi in ALWAYS:
        wanted.update(c for c in range(lo, hi + 1) if c in cmap)
    wanted.update(c for c in range(0x20, 0x7F) if c in cmap)
    wanted.update(c for c in EXTRA if c in cmap)

    options = Options()
    options.flavor = 'woff2'
    options.desubroutinize = True
    options.layout_features = ['*']
    options.name_IDs = ['*']
    options.notdef_outline = True
    subsetter = Subsetter(options=options)
    subsetter.populate(unicodes=sorted(wanted))
    subsetter.subset(font)
    font.flavor = 'woff2'
    font.save(str(TARGET))

    after = TARGET.stat().st_size
    print(f'  characters kept: {len(wanted)} of {len(cmap)}')
    print(f'  {before:,} -> {after:,} bytes ({after / before:.0%})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
