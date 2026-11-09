import hashlib
import tempfile
import unittest
from pathlib import Path

from tds_lite.download import (
    DownloadError,
    _is_media_file,
    _sha256_file,
    download_media,
    needs_extractor,
)


class TestUrlDetection(unittest.TestCase):
    def test_youtube_needs_extractor(self):
        for url in (
            "https://www.youtube.com/watch?v=abc123",
            "https://youtu.be/abc123",
            "https://m.youtube.com/watch?v=abc123",
        ):
            self.assertTrue(needs_extractor(url), url)

    def test_direct_media_does_not_need_extractor(self):
        for url in (
            "https://example.com/video.mp4",
            "https://example.com/video.webm?x=1",
            "https://example.com/video.mkv",
        ):
            self.assertFalse(needs_extractor(url), url)

    def test_page_without_media_suffix_needs_extractor(self):
        self.assertTrue(needs_extractor("https://example.com/watch?v=1"))
        self.assertTrue(needs_extractor("https://example.com/download.php?id=1"))

    def test_non_http_rejected(self):
        with self.assertRaises(DownloadError):
            download_media("ftp://example.com/video.mp4", ".")


class TestMediaDetection(unittest.TestCase):
    def _write(self, data: bytes) -> Path:
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.write(data)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return Path(handle.name)

    def test_mp4(self):
        path = self._write(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32)
        self.assertTrue(_is_media_file(path))

    def test_webm(self):
        path = self._write(b"\x1aE\xdf\xa3" + b"\x00" * 32)
        self.assertTrue(_is_media_file(path))

    def test_avi(self):
        path = self._write(b"RIFF\x00\x00\x00\x00AVI " + b"\x00" * 32)
        self.assertTrue(_is_media_file(path))

    def test_html_rejected(self):
        path = self._write(b"<!DOCTYPE html><html><body>no</body></html>")
        self.assertFalse(_is_media_file(path))

    def test_empty_rejected(self):
        path = self._write(b"")
        self.assertFalse(_is_media_file(path))

    def test_sha256(self):
        data = b"todus-lite"
        path = self._write(data)
        self.assertEqual(_sha256_file(path), hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()
