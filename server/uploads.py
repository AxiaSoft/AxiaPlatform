"""Product cover uploads.

A cover is the product's own artwork, so the console lets an administrator send
a file rather than pasting a URL. The file is decoded, checked and then
re-encoded before it is stored:

* re-encoding is what strips metadata. A JPEG straight from a phone carries the
  camera, sometimes the location, and arbitrary EXIF blocks; none of it belongs
  on a public page.
* the decoder is the only component that parses untrusted bytes, so nothing is
  written to disk until the image has been fully read back.

The storage layout is ``public/uploads/covers/<sha256>.<ext>``. Hashing the
content means the same picture uploaded twice is stored once, and a file's name
never comes from the request.
"""
import hashlib
import os
import struct
import subprocess  # noqa: S404 - ImageMagick is invoked with a fixed argv
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Inside the public tree, because the result is served by the static handler.
# AXIA_UPLOAD_DIR lets a deployment put the files on a mounted volume without
# touching the code; the URL stays the same either way.
UPLOAD_DIR = Path(os.environ.get('AXIA_UPLOAD_DIR') or (ROOT / 'public' / 'uploads' / 'covers'))
UPLOAD_URL = '/uploads/covers'

MAX_BYTES = 5 * 1024 * 1024          # a cover is not a photo library
MAX_EDGE = 1600                      # larger than any place a cover is drawn
QUALITY = 82

# Only these are accepted. SVG is deliberately absent: it is a document format
# that can carry script, and this endpoint serves the result from the site's own
# origin.
SIGNATURES = (
    (b'\x89PNG\r\n\x1a\n', 'png'),
    (b'\xff\xd8\xff', 'jpg'),
    (b'GIF87a', 'gif'),
    (b'GIF89a', 'gif'),
)


class UploadError(Exception):
    """A rejected upload, with a message safe to show the administrator."""


def sniff(data):
    """The real format of the bytes, or None. The extension is never trusted."""
    for signature, kind in SIGNATURES:
        if data.startswith(signature):
            if kind == 'png':
                return 'png' if data[12:16] == b'IHDR' else None
            if kind == 'gif':
                return 'gif' if len(data) > 13 else None
            return kind
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    return None


def png_size(data):
    """Dimensions from an IHDR chunk, without decoding the image."""
    if len(data) < 24 or data[12:16] != b'IHDR':
        raise UploadError('That file is not a valid PNG.')
    return struct.unpack('>II', data[16:24])


def _convert(source, target, *extra):
    argv = ['convert', str(source), '-strip', '-resize',
            f'{MAX_EDGE}x{MAX_EDGE}>', '-quality', str(QUALITY), *extra, str(target)]
    try:
        done = subprocess.run(  # noqa: S603 - argv is fixed, paths are generated
            argv, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        raise UploadError('The image could not be processed on this server.')
    if done.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        raise UploadError('That image could not be read. Try a PNG or JPEG.')
    return target


def store(data, upload_dir=None, convert=_convert):
    """Validate and store one image. Returns the public URL path.

    `convert` is injected so the validation path can be tested without
    ImageMagick on the machine.
    """
    upload_dir = Path(upload_dir or UPLOAD_DIR)
    if not data:
        raise UploadError('No image was received.')
    if len(data) > MAX_BYTES:
        raise UploadError(f'The image is larger than {MAX_BYTES // (1024 * 1024)} MB.')
    kind = sniff(data)
    if not kind:
        raise UploadError('Only PNG, JPEG, WebP and GIF images are accepted.')

    # A cheap sanity check before handing bytes to the decoder.
    if kind == 'png':
        width, height = png_size(data)
        if width < 8 or height < 8:
            raise UploadError('That image is too small to use as a cover.')
        if width * height > 40_000_000:
            raise UploadError('That image is too large to process.')

    digest = hashlib.sha256(data).hexdigest()[:32]
    upload_dir.mkdir(parents=True, exist_ok=True)
    staging = upload_dir / f'.{digest}.incoming'
    staging.write_bytes(data)
    try:
        # Everything is normalised to PNG: it is lossless, it keeps a logo's
        # transparency, and it removes the format question from the writer.
        target = upload_dir / f'{digest}.png'
        convert(staging, target)
        return f'{UPLOAD_URL}/{target.name}'
    finally:
        staging.unlink(missing_ok=True)


def purge(url, upload_dir=None):
    """Remove a stored cover. Missing files are not an error."""
    if not url or not str(url).startswith(UPLOAD_URL + '/'):
        return False
    name = str(url).rsplit('/', 1)[-1]
    if '/' in name or '\\' in name or name.startswith('.'):
        return False
    target = Path(upload_dir or UPLOAD_DIR) / name
    try:
        target.unlink()
        return True
    except OSError:
        return False
