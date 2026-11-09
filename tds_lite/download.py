"""Descarga directa por HTTP(S) con limite de tamano y hash al vuelo."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class DownloadError(Exception):
    """Error de descarga."""


def human_bytes(value: float) -> str:
    units = ["B", "KiB", "MiB", "GiB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{value:.0f} B"


def _guess_name(url: str) -> str:
    path = unquote(urlparse(url).path)
    name = os.path.basename(path)
    if not name or name in {"/", "."}:
        name = "video.bin"
    # Limita caracteres raros para no romper rutas.
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    return safe[-80:] or "video.bin"


def download(
    url: str,
    dest_dir: str | Path,
    max_bytes: int | None = None,
    timeout: float = 60.0,
    show_progress: bool = True,
) -> tuple[Path, int, str]:
    """Descarga ``url`` en ``dest_dir``.

    Devuelve ``(ruta, bytes, sha256_hex)``. Aplica un limite estricto de
    ``max_bytes`` y aborta si el contenido es HTML (enlace no directo).
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise DownloadError("el enlace debe empezar por http:// o https://")
    if not parsed.netloc:
        raise DownloadError("el enlace no tiene host valido")

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    target = dest / f"{stamp}_{_guess_name(url)}"
    partial = target.with_suffix(target.suffix + ".part")

    request = Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        },
    )

    hasher = hashlib.sha256()
    written = 0
    started = time.monotonic()
    last_report = 0.0

    try:
        with urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise DownloadError(f"el servidor devolvio HTTP {status}")
            content_type = (response.headers.get("Content-Type") or "").lower()
            if content_type.startswith("text/html"):
                raise DownloadError(
                    "el enlace devolvio HTML, no un fichero. "
                    "Usa el enlace directo de descarga del video."
                )
            length_header = response.headers.get("Content-Length")
            length = int(length_header) if length_header and length_header.isdigit() else 0
            if max_bytes is not None and length > max_bytes:
                raise DownloadError(
                    f"el fichero pesa {human_bytes(length)} y el limite es "
                    f"{human_bytes(max_bytes)} (ajusta MAX_VIDEO_BYTES)"
                )

            with open(partial, "wb") as out:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    written += len(chunk)
                    if max_bytes is not None and written > max_bytes:
                        raise DownloadError(
                            f"la descarga supera el límite de "
                            f"{human_bytes(max_bytes)}"
                        )
                    out.write(chunk)
                    hasher.update(chunk)
                    if show_progress:
                        now = time.monotonic()
                        if now - last_report >= 0.5 or written == length:
                            last_report = now
                            elapsed = max(now - started, 1e-6)
                            rate = written / elapsed
                            if length:
                                pct = written * 100.0 / length
                                line = (
                                    f"\rDescargando {human_bytes(written)} / "
                                    f"{human_bytes(length)} ({pct:5.1f}%) "
                                    f"{human_bytes(rate)}/s"
                                )
                            else:
                                line = (
                                    f"\rDescargando {human_bytes(written)} "
                                    f"{human_bytes(rate)}/s"
                                )
                            print(line, end="", file=sys.stderr, flush=True)
        if show_progress:
            print(file=sys.stderr)
        if written == 0:
            raise DownloadError("el fichero descargado esta vacio")
        partial.replace(target)
    except HTTPError as exc:
        _cleanup(partial)
        raise DownloadError(f"HTTP {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        _cleanup(partial)
        raise DownloadError(f"no se pudo descargar: {exc.reason}") from exc
    except OSError as exc:
        _cleanup(partial)
        raise DownloadError(f"error de red/fichero: {exc}") from exc
    except Exception:
        _cleanup(partial)
        raise

    return target, written, hasher.hexdigest()


MEDIA_SUFFIXES = {
    ".mp4", ".m4v", ".mkv", ".webm", ".avi", ".mov", ".flv",
    ".mpg", ".mpeg", ".3gp", ".ts", ".m2ts", ".ogv",
}

_EXTRACTOR_HOSTS = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "tiktok.com",
    "instagram.com",
    "facebook.com",
    "fb.watch",
    "twitter.com",
    "x.com",
    "vimeo.com",
    "dailymotion.com",
    "twitch.tv",
    "soundcloud.com",
)


def has_ytdlp() -> bool:
    return importlib.util.find_spec("yt_dlp") is not None


def _is_extractor_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _EXTRACTOR_HOSTS)


def needs_extractor(url: str) -> bool:
    """True si el enlace es una pagina que necesita yt-dlp."""
    if _is_extractor_host(url):
        return True
    return Path(urlparse(url).path).suffix.lower() not in MEDIA_SUFFIXES


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _is_media_file(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return False
    if not head:
        return False
    if head[:1] == b"<" or head.lower().startswith((b"<!doctype", b"<html")):
        return False
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return True
    if head.startswith(b"\x1aE\xdf\xa3"):
        return True
    if head.startswith(b"RIFF") and head[8:12] == b"AVI ":
        return True
    if head.startswith(b"FLV"):
        return True
    if head.startswith((b"\x00\x00\x01\xba", b"\x00\x00\x01\xb3")):
        return True
    if head.startswith(b"OggS"):
        return True
    return False


def _cleanup_stamp(dest: Path, stamp: str) -> None:
    for path in dest.glob(f"{stamp}_*"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _download_with_ytdlp(
    url: str,
    dest_dir: str | Path,
    max_bytes: int | None = None,
    cookies: str | Path | None = None,
    cookies_from_browser: str | None = None,
    show_progress: bool = True,
) -> tuple[Path, int, str]:
    """Descarga con yt-dlp (YouTube, TikTok, ...) y devuelve ruta, bytes y SHA."""
    try:
        import yt_dlp
    except ImportError as exc:
        raise DownloadError(
            "yt-dlp no esta instalado. Instala con: "
            "python3 -m pip install --user yt-dlp"
        ) from exc

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    outtmpl = str(dest / f"{stamp}_%(title).80s_%(id)s.%(ext)s")
    ffmpeg = shutil.which("ffmpeg") is not None
    if ffmpeg:
        fmt = (
            "bv*[ext=mp4][height<=480]+ba[ext=m4a]"
            "/b[ext=mp4][height<=480][vcodec!=none]"
            "/bv*[height<=480]+ba"
            "/b[height<=480][vcodec!=none]"
            "/bv*[vcodec!=none]+ba"
            "/b[vcodec!=none]"
        )
    else:
        fmt = (
            "b[ext=mp4][height<=480][vcodec!=none]"
            "/b[height<=480][vcodec!=none]"
            "/b[vcodec!=none]"
        )

    options: dict = {
        "outtmpl": outtmpl,
        "format": fmt,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "restrictfilenames": True,
        "overwrites": True,
        "merge_output_format": "mp4",
    }
    if max_bytes is not None:
        options["max_filesize"] = max_bytes
    if cookies:
        options["cookiefile"] = str(Path(cookies).expanduser())
    if cookies_from_browser:
        options["cookiesfrombrowser"] = (cookies_from_browser,)
    deno = shutil.which("deno")
    if not deno:
        candidate = Path.home() / ".deno" / "bin" / "deno"
        if candidate.is_file():
            deno = str(candidate)
    if deno:
        options["js_runtimes"] = {"deno": {"path": deno}}
    if show_progress:
        last = {"time": 0.0}

        def hook(data: dict) -> None:
            if data.get("status") == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                done = data.get("downloaded_bytes") or 0
                now = time.monotonic()
                if now - last["time"] < 0.5:
                    return
                last["time"] = now
                if total:
                    pct = done * 100.0 / total
                    line = (
                        f"\rDescargando {human_bytes(done)} / "
                        f"{human_bytes(total)} ({pct:5.1f}%)"
                    )
                else:
                    line = f"\rDescargando {human_bytes(done)}"
                print(line, end="", file=sys.stderr, flush=True)
            elif data.get("status") == "finished":
                print(file=sys.stderr)

        options["progress_hooks"] = [hook]

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)
    except DownloadError:
        raise
    except Exception as exc:
        _cleanup_stamp(dest, stamp)
        raise DownloadError(f"yt-dlp fallo: {exc}") from exc

    if show_progress:
        print(file=sys.stderr)
    candidates = [
        p
        for p in dest.glob(f"{stamp}_*")
        if p.is_file() and not p.name.endswith((".part", ".ytdl"))
    ]
    if not candidates:
        raise DownloadError(
            "yt-dlp no genero ningun fichero (puede que el video supere el "
            "limite o requiera iniciar sesion/cookies)"
        )
    path = max(candidates, key=lambda p: p.stat().st_size)
    for other in candidates:
        if other != path:
            try:
                other.unlink(missing_ok=True)
            except OSError:
                pass
    size = path.stat().st_size
    if size == 0:
        path.unlink(missing_ok=True)
        raise DownloadError("el video descargado esta vacio")
    if max_bytes is not None and size > max_bytes:
        path.unlink(missing_ok=True)
        raise DownloadError(
            f"el video pesa {human_bytes(size)} y el limite es "
            f"{human_bytes(max_bytes)} (ajusta MAX_VIDEO_BYTES)"
        )
    if not _is_media_file(path):
        path.unlink(missing_ok=True)
        raise DownloadError(
            "yt-dlp no produjo un video valido (posible HTML o formato raro)"
        )
    return path, size, _sha256_file(path)


def download_media(
    url: str,
    dest_dir: str | Path,
    max_bytes: int | None = None,
    timeout: float = 60.0,
    show_progress: bool = True,
    cookies: str | Path | None = None,
    cookies_from_browser: str | None = None,
) -> tuple[Path, int, str]:
    """Descarga un enlace directo o una pagina soportada por yt-dlp."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise DownloadError("el enlace debe empezar por http:// o https://")
    if not parsed.netloc:
        raise DownloadError("el enlace no tiene host valido")

    if needs_extractor(url):
        if not has_ytdlp():
            if _is_extractor_host(url):
                raise DownloadError(
                    "este enlace necesita yt-dlp (YouTube/TikTok/...). "
                    "Instala con: python3 -m pip install --user yt-dlp"
                )
        else:
            return _download_with_ytdlp(
                url,
                dest_dir,
                max_bytes,
                cookies=cookies,
                cookies_from_browser=cookies_from_browser,
                show_progress=show_progress,
            )

    try:
        return download(
            url,
            dest_dir,
            max_bytes=max_bytes,
            timeout=timeout,
            show_progress=show_progress,
        )
    except DownloadError as exc:
        if has_ytdlp() and "HTML" in str(exc):
            print(
                "Aviso: el enlace devolvio HTML; reintentando con yt-dlp...",
                file=sys.stderr,
            )
            return _download_with_ytdlp(
                url,
                dest_dir,
                max_bytes,
                cookies=cookies,
                cookies_from_browser=cookies_from_browser,
                show_progress=show_progress,
            )
        raise


def _cleanup(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
