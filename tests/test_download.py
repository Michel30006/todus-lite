import hashlib
import http.server
import tempfile
import threading
import unittest
from pathlib import Path

from tds_lite.download import (
    DownloadError,
    _is_media_file,
    _sha256_file,
    _url_key,
    _ytdlp_format,
    download,
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


class TestQualityFormat(unittest.TestCase):
    def test_360_limits_height(self):
        fmt = _ytdlp_format(360)
        self.assertIn("[height<=360]", fmt)
        self.assertNotIn("[height<=480]", fmt)

    def test_480_limits_height(self):
        fmt = _ytdlp_format(480)
        self.assertIn("[height<=480]", fmt)

    def test_720_limits_height(self):
        fmt = _ytdlp_format(720)
        self.assertIn("[height<=720]", fmt)
        self.assertNotIn("[height<=480]", fmt)

    def test_without_ffmpeg_uses_combined_format(self):
        fmt = _ytdlp_format(720, merge=False)
        self.assertNotIn("+ba", fmt)
        self.assertIn("b[ext=mp4][height<=720][vcodec!=none]", fmt)

    def test_avoids_audio_only_fallback(self):
        for height in (360, 480, 720):
            fmt = _ytdlp_format(height)
            self.assertEqual(fmt.count("[vcodec!=none]"), 2)


class TestResumeDownload(unittest.TestCase):
    BODY = bytes(range(256)) * 256

    def _serve(self, handler):
        class QuietServer(http.server.ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                pass

        server = QuietServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        return f"http://127.0.0.1:{port}/video.mp4"

    def test_resumes_existing_partial(self):
        body = self.BODY
        half = len(body) // 2

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                data = body
                start = 0
                rng = self.headers.get("Range")
                if rng:
                    start = int(rng.split("=", 1)[1].split("-", 1)[0])
                payload = data[start:]
                self.send_response(206 if start else 200)
                if start:
                    self.send_header(
                        "Content-Range",
                        f"bytes {start}-{len(data) - 1}/{len(data)}",
                    )
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, fmt, *args):
                pass

        url = self._serve(Handler)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            partial = dest / f".tds-{_url_key(url)}.part"
            partial.write_bytes(body[:half])
            path, size, digest = download(
                url, dest, show_progress=False, attempts=1
            )
            self.assertEqual(path.read_bytes(), body)
            self.assertEqual(size, len(body))
            self.assertEqual(digest, hashlib.sha256(body).hexdigest())
            self.assertFalse(partial.exists())

    def test_retries_after_connection_drop(self):
        body = self.BODY
        state = {"calls": 0}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                state["calls"] += 1
                data = body
                start = 0
                rng = self.headers.get("Range")
                if rng:
                    start = int(rng.split("=", 1)[1].split("-", 1)[0])
                if state["calls"] == 1 and not rng:
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data[: len(data) // 2])
                    self.wfile.flush()
                    self.close_connection = True
                    return
                payload = data[start:]
                self.send_response(206 if start else 200)
                if start:
                    self.send_header(
                        "Content-Range",
                        f"bytes {start}-{len(data) - 1}/{len(data)}",
                    )
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, fmt, *args):
                pass

        url = self._serve(Handler)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            path, size, digest = download(
                url,
                dest,
                show_progress=False,
                attempts=3,
                retry_delay=0,
            )
            self.assertGreaterEqual(state["calls"], 2)
            self.assertEqual(path.read_bytes(), body)
            self.assertEqual(size, len(body))
            self.assertEqual(digest, hashlib.sha256(body).hexdigest())


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
