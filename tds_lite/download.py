"""Descarga directa por HTTP(S) y con yt-dlp, con calidad y hash al vuelo."""

from __future__ import annotations

import hashlib
import http.client
import importlib.util
import os
import re
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


def _url_key(url: str) -> str:
    """Clave estable por URL para reanudar descargas."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


class _RetryDownload(DownloadError):
    """Fallo transitorio que se puede reanudar con HTTP Range."""


def _content_range_total(value: str) -> int:
    match = re.match(r"bytes\s+(?:\d+-\d+|\*)/(\d+)", value.strip())
    return int(match.group(1)) if match else 0


def download(
    url: str,
    dest_dir: str | Path,
    max_bytes: int | None = None,
    timeout: float = 60.0,
    show_progress: bool = True,
    attempts: int = 4,
    retry_delay: float = 1.0,
) -> tuple[Path, int, str]:
    """Descarga ``url`` en ``dest_dir``, reanudando si se corta la conexion.

    Usa un fichero ``.part`` estable por URL y peticiones HTTP ``Range``. Si
    la red falla, reintenta y continua desde el ultimo byte. Si ``max_bytes``
    es distinto de cero, aplica un limite estricto. El fichero parcial se
    conserva al agotar los reintentos: otra ejecucion lo reanuda.
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
    partial = dest / f".tds-{_url_key(url)}.part"
    attempts = max(1, int(attempts))
    retry_delay = max(0.0, float(retry_delay))
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        existing = partial.stat().st_size if partial.is_file() else 0
        if max_bytes and existing > max_bytes:
            _cleanup(partial)
            raise DownloadError(
                f"el fichero parcial pesa {human_bytes(existing)} y el limite es "
                f"{human_bytes(max_bytes)} (ajusta MAX_VIDEO_BYTES)"
            )

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        }
        if existing:
            headers["Range"] = f"bytes={existing}-"
        request = Request(url, headers=headers)

        try:
            with urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                content_type = (response.headers.get("Content-Type") or "").lower()
                if content_type.startswith("text/html"):
                    _cleanup(partial)
                    raise DownloadError(
                        "el enlace devolvio HTML, no un fichero. "
                        "Usa el enlace directo de descarga del video."
                    )

                if status == 206:
                    content_range = response.headers.get("Content-Range") or ""
                    match = re.match(
                        r"bytes\s+(\d+)-(\d+)/(\d+|\*)", content_range
                    )
                    if not match:
                        raise _RetryDownload(
                            "respuesta 206 sin Content-Range valido"
                        )
                    start = int(match.group(1))
                    if start != existing:
                        raise _RetryDownload(
                            f"el servidor reanudo en {start}, esperaba {existing}"
                        )
                    total = 0 if match.group(3) == "*" else int(match.group(3))
                elif status == 200:
                    if existing:
                        # El servidor ignoro Range: hay que empezar de cero.
                        existing = 0
                    length_header = response.headers.get("Content-Length")
                    total = (
                        int(length_header)
                        if length_header and length_header.isdigit()
                        else 0
                    )
                else:
                    raise DownloadError(f"el servidor devolvio HTTP {status}")

                if max_bytes and total > max_bytes:
                    _cleanup(partial)
                    raise DownloadError(
                        f"el fichero pesa {human_bytes(total)} y el limite es "
                        f"{human_bytes(max_bytes)} (ajusta MAX_VIDEO_BYTES)"
                    )

                written = existing
                started = time.monotonic()
                last_report = 0.0
                mode = "ab" if existing else "wb"
                with open(partial, mode) as out:
                    while True:
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        written += len(chunk)
                        if max_bytes and written > max_bytes:
                            _cleanup(partial)
                            raise DownloadError(
                                f"la descarga supera el límite de "
                                f"{human_bytes(max_bytes)}"
                            )
                        out.write(chunk)
                        if show_progress:
                            now = time.monotonic()
                            if now - last_report >= 0.5 or (total and written >= total):
                                last_report = now
                                elapsed = max(now - started, 1e-6)
                                rate = (written - existing) / elapsed
                                if total:
                                    pct = written * 100.0 / total
                                    line = (
                                        f"\rDescargando {human_bytes(written)} / "
                                        f"{human_bytes(total)} ({pct:5.1f}%) "
                                        f"{human_bytes(rate)}/s"
                                    )
                                    if existing:
                                        line += (
                                            f" (reanudado en {human_bytes(existing)})"
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
                if total and written < total:
                    raise _RetryDownload(
                        f"descarga incompleta: {written}/{total} bytes"
                    )
                if total and written > total:
                    raise _RetryDownload(
                        f"descarga con bytes de mas: {written}/{total}"
                    )

                partial.replace(target)
                return target, written, _sha256_file(target)

        except HTTPError as exc:
            if exc.code == 416 and existing:
                total = _content_range_total(
                    (exc.headers.get("Content-Range") if exc.headers else "") or ""
                )
                if total and existing == total:
                    partial.replace(target)
                    return target, existing, _sha256_file(target)
                _cleanup(partial)
                last_error = exc
                if attempt < attempts:
                    if retry_delay:
                        time.sleep(retry_delay * attempt)
                    continue
                raise DownloadError(
                    "HTTP 416: el servidor rechazo la reanudacion"
                ) from exc

            if exc.code in {408, 425, 429, 500, 502, 503, 504} and attempt < attempts:
                last_error = exc
                if retry_delay:
                    time.sleep(retry_delay * attempt)
                continue
            raise DownloadError(f"HTTP {exc.code}: {exc.reason}") from exc

        except _RetryDownload as exc:
            last_error = exc
            if attempt < attempts:
                if retry_delay:
                    time.sleep(retry_delay * attempt)
                continue
            raise DownloadError(
                f"{exc} (se conserva {partial.name}; vuelve a ejecutar para reanudar)"
            ) from exc

        except (URLError, OSError, http.client.HTTPException) as exc:
            last_error = exc
            if attempt < attempts:
                if retry_delay:
                    time.sleep(retry_delay * attempt)
                continue
            raise DownloadError(
                f"no se pudo descargar: {exc} "
                f"(se conserva {partial.name}; vuelve a ejecutar para reanudar)"
            ) from exc

    raise DownloadError(f"no se pudo descargar: {last_error}")


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


def _ytdlp_format(max_height: int | None = 480, *, merge: bool = True) -> str:
    """Selector de yt-dlp limitado a la altura maxima pedida."""
    height = f"[height<={max_height}]" if max_height else ""
    if merge:
        return (
            f"bv*[ext=mp4]{height}+ba[ext=m4a]"
            f"/b[ext=mp4]{height}[vcodec!=none]"
            f"/bv*{height}+ba"
            f"/b{height}[vcodec!=none]"
        )
    return f"b[ext=mp4]{height}[vcodec!=none]/b{height}[vcodec!=none]"


def _download_with_ytdlp(
    url: str,
    dest_dir: str | Path,
    max_bytes: int | None = None,
    max_height: int = 480,
    cookies: str | Path | None = None,
    cookies_from_browser: str | None = None,
    show_progress: bool = True,
    player_client: str | None = None,
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
    work = dest / f".tds-ytdlp-{_url_key(url)}-{max_height or 'best'}"
    work.mkdir(parents=True, exist_ok=True)
    outtmpl = str(work / "%(title).80s_%(id)s.%(ext)s")
    ffmpeg = shutil.which("ffmpeg") is not None
    fmt = _ytdlp_format(max_height, merge=ffmpeg)

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
        "continuedl": True,
        "nopart": False,
        "merge_output_format": "mp4",
    }
    if max_bytes:
        options["max_filesize"] = max_bytes
    if cookies:
        options["cookiefile"] = str(Path(cookies).expanduser())
    if cookies_from_browser:
        options["cookiesfrombrowser"] = (cookies_from_browser,)
    if player_client:
        options["extractor_args"] = {"youtube": {"player_client": [player_client]}}
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
        try:
            if work.is_dir() and not any(work.iterdir()):
                work.rmdir()
        except OSError:
            pass
        raise DownloadError(
            f"yt-dlp fallo: {exc}. Si se interrumpio, vuelve a ejecutar: "
            "la descarga continuara donde se quedo."
        ) from exc

    if show_progress:
        print(file=sys.stderr)
    candidates = [
        p
        for p in work.glob("*")
        if p.is_file() and not p.name.endswith((".part", ".ytdl"))
    ]
    if not candidates:
        raise DownloadError(
            "yt-dlp no genero ningun fichero (puede que la calidad pedida "
            "no exista o requiera iniciar sesion/cookies)"
        )
    path = max(candidates, key=lambda p: p.stat().st_size)
    target = dest / f"{stamp}_{path.name}"
    path.replace(target)
    for other in candidates:
        if other != path:
            try:
                other.unlink(missing_ok=True)
            except OSError:
                pass
    shutil.rmtree(work, ignore_errors=True)
    path = target
    size = path.stat().st_size
    if size == 0:
        path.unlink(missing_ok=True)
        raise DownloadError("el video descargado esta vacio")
    if max_bytes and size > max_bytes:
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
    max_height: int = 480,
    timeout: float = 60.0,
    show_progress: bool = True,
    cookies: str | Path | None = None,
    cookies_from_browser: str | None = None,
) -> tuple[Path, int, str]:
    """Descarga un enlace directo o una pagina soportada por yt-dlp.

    ``max_height`` limita la altura del video (360, 480, 720...). Si
    ``max_bytes`` es ``None`` o ``0`` no hay limite de tamano.
    """
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
            client = os.environ.get("TDS_YTDLP_PLAYER_CLIENT") or None
            try:
                return _download_with_ytdlp(
                    url,
                    dest_dir,
                    max_bytes,
                    max_height=max_height,
                    cookies=cookies,
                    cookies_from_browser=cookies_from_browser,
                    show_progress=show_progress,
                    player_client=client,
                )
            except DownloadError as exc:
                msg = str(exc)
                retryable = (
                    _is_extractor_host(url)
                    and client is None
                    and any(
                        token in msg
                        for token in (
                            "403",
                            "Only images",
                            "Requested format is not available",
                        )
                    )
                )
                if not retryable:
                    raise
                print(
                    "Aviso: reintentando YouTube con cliente web_embedded...",
                    file=sys.stderr,
                )
                return _download_with_ytdlp(
                    url,
                    dest_dir,
                    max_bytes,
                    max_height=max_height,
                    cookies=cookies,
                    cookies_from_browser=cookies_from_browser,
                    show_progress=show_progress,
                    player_client="web_embedded",
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
                max_height=max_height,
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
