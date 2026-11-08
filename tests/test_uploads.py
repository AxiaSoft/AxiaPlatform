"""Product cover uploads: what is accepted, and what is refused."""
import io
import os
import struct
import sys
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import uploads  # noqa: E402


def png_bytes(width=40, height=40):
    """A minimal, real PNG — enough for the sniffer and the size check."""
    raw = b''
    for _ in range(height):
        raw += b'\x00' + bytes([120, 160, 220]) * width
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data +
                struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF))
    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) +
            chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


class SniffTest(unittest.TestCase):
    def test_png_is_recognised(self):
        self.assertEqual(uploads.sniff(png_bytes()), 'png')

    def test_jpeg_is_recognised(self):
        self.assertEqual(uploads.sniff(b'\xff\xd8\xff\xe0' + b'\x00' * 40), 'jpg')

    def test_webp_is_recognised(self):
        self.assertEqual(uploads.sniff(b'RIFF' + b'\x00' * 4 + b'WEBP' + b'\x00' * 8), 'webp')

    def test_svg_is_refused(self):
        # SVG can carry script and would be served from the site's own origin.
        self.assertIsNone(uploads.sniff(b'<svg xmlns="http://www.w3.org/2000/svg"/>'))

    def test_html_is_refused(self):
        self.assertIsNone(uploads.sniff(b'<html><script>alert(1)</script>'))

    def test_a_png_signature_without_a_header_is_refused(self):
        self.assertIsNone(uploads.sniff(b'\x89PNG\r\n\x1a\n' + b'\x00' * 20))


class StoreTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.dir = Path(tempfile.mkdtemp())
        self.calls = []

    def fake_convert(self, source, target, *extra):
        # Stand in for ImageMagick: copy the bytes through so the store path can
        # be tested on a machine without it.
        self.calls.append((source.name, target.name))
        target.write_bytes(source.read_bytes())
        return target

    def test_a_png_is_stored_under_a_content_hash(self):
        url = uploads.store(png_bytes(), upload_dir=self.dir, convert=self.fake_convert)
        self.assertRegex(url, r'^/uploads/covers/[0-9a-f]{32}\.png$')
        self.assertTrue((self.dir / url.rsplit('/', 1)[-1]).is_file())

    def test_the_same_image_is_stored_once(self):
        a = uploads.store(png_bytes(), upload_dir=self.dir, convert=self.fake_convert)
        b = uploads.store(png_bytes(), upload_dir=self.dir, convert=self.fake_convert)
        self.assertEqual(a, b)
        self.assertEqual(len([p for p in self.dir.iterdir() if p.suffix == '.png']), 1)

    def test_the_staging_file_is_always_removed(self):
        uploads.store(png_bytes(), upload_dir=self.dir, convert=self.fake_convert)
        self.assertEqual([p.name for p in self.dir.iterdir() if '.incoming' in p.name], [])

    def test_staging_is_removed_when_conversion_fails(self):
        def failing(source, target, *extra):
            raise uploads.UploadError('nope')
        with self.assertRaises(uploads.UploadError):
            uploads.store(png_bytes(), upload_dir=self.dir, convert=failing)
        self.assertEqual([p.name for p in self.dir.iterdir() if '.incoming' in p.name], [])

    def test_empty_input_is_refused(self):
        with self.assertRaises(uploads.UploadError):
            uploads.store(b'', upload_dir=self.dir, convert=self.fake_convert)

    def test_an_oversized_file_is_refused_before_decoding(self):
        with self.assertRaises(uploads.UploadError) as caught:
            uploads.store(b'\x89PNG\r\n\x1a\n' + b'0' * (uploads.MAX_BYTES + 1),
                          upload_dir=self.dir, convert=self.fake_convert)
        self.assertIn('larger than', str(caught.exception))
        self.assertEqual(self.calls, [])

    def test_a_tiny_png_is_refused(self):
        with self.assertRaises(uploads.UploadError):
            uploads.store(png_bytes(4, 4), upload_dir=self.dir, convert=self.fake_convert)

    def test_an_absurd_pixel_count_is_refused(self):
        # A 40k x 40k header is small on disk and enormous in memory: the check
        # has to happen before the decoder allocates.
        data = bytearray(png_bytes(40, 40))
        data[16:24] = struct.pack('>II', 40000, 40000)
        with self.assertRaises(uploads.UploadError):
            uploads.store(bytes(data), upload_dir=self.dir, convert=self.fake_convert)

    def test_the_name_never_comes_from_the_request(self):
        url = uploads.store(png_bytes(), upload_dir=self.dir, convert=self.fake_convert)
        self.assertNotIn('..', url)
        self.assertNotIn(' ', url)


class PurgeTest(unittest.TestCase):
    def test_a_stored_cover_can_be_removed(self):
        import tempfile
        from pathlib import Path
        d = Path(tempfile.mkdtemp())
        (d / 'abc.png').write_bytes(b'x')
        self.assertTrue(uploads.purge('/uploads/covers/abc.png', upload_dir=d))
        self.assertFalse((d / 'abc.png').exists())

    def test_a_path_outside_the_upload_folder_is_refused(self):
        import tempfile
        from pathlib import Path
        d = Path(tempfile.mkdtemp())
        self.assertFalse(uploads.purge('/uploads/covers/../../secret.png', upload_dir=d))
        self.assertFalse(uploads.purge('/brand/axiasoft-original.png', upload_dir=d))

    def test_a_missing_file_is_not_an_error(self):
        import tempfile
        from pathlib import Path
        self.assertFalse(uploads.purge('/uploads/covers/nope.png', upload_dir=Path(tempfile.mkdtemp())))


if __name__ == '__main__':
    unittest.main()
