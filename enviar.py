#!/usr/bin/env python3
"""Emisor ligero: descarga un video, lo codifica y lo envia por ToDus.

Uso interactivo (lo normal en el codespace):

    python3 enviar.py

El script pide el enlace del video y el numero de destino, descarga el fichero,
lo convierte al texto de la tabla v1 y lo envia en tramas TDS1 por ToDus.

El receptor (receptor.py o el binario C++ tds_receiver del kkk) debe estar
escuchando ANTES de lanzar el envio. Este script espera unos segundos tras
conectar para dar tiempo a que el receptor este listo.

Variables de entorno utiles:
    TODUS_SENDER        numero emisor (def. 58799457; se normaliza con 53)
    TODUS_AUTH_URL      endpoint de token (def. https://auth.todus.cu/v2/auth/token)
    MAX_VIDEO_BYTES     limite de descarga en bytes (def. 26214400 = 25 MiB)
    SEND_DELAY_MS       pausa entre tramas (def. 120 ms)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from tds_lite.download import (
    DownloadError,
    download_media,
    human_bytes,
)
from tds_lite.protocol import (
    MAX_STANZA_BYTES,
    ProtocolError,
    build_frames,
    local_part,
    normalize_number,
)
from tds_lite.todus import AUTH_URL, TodusError, XmppClient

DEFAULT_RECIPIENT = "58548838"
DEFAULT_SENDER = "58799457"
DEFAULT_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_SEND_DELAY_MS = 120
DEFAULT_ACK_TIMEOUT = 15.0
DEFAULT_RETRIES = 3
DEFAULT_COOKIES = Path.home() / ".config" / "tds" / "cookies.txt"


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _ask(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{text}{suffix}: ").strip()
    except EOFError:
        raise SystemExit("Entrada cancelada.")
    return answer or default


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descarga un video, lo codifica y lo envia por ToDus."
    )
    parser.add_argument(
        "--url",
        help="enlace del video (directo o YouTube/TikTok con yt-dlp)",
    )
    parser.add_argument(
        "--cookies",
        help=(
            "fichero de cookies Netscape para yt-dlp "
            "(def. ~/.config/tds/cookies.txt o $TDS_COOKIES_FILE)"
        ),
    )
    parser.add_argument(
        "--cookies-from-browser",
        help="navegador del que tomar cookies (chrome, firefox, ...)",
    )
    parser.add_argument("--file", help="fichero local ya descargado (omite descarga)")
    parser.add_argument("--to", help=f"numero destino (def. {DEFAULT_RECIPIENT})")
    parser.add_argument(
        "--from",
        dest="sender",
        help=f"numero emisor ToDus (def. {DEFAULT_SENDER} o $TODUS_SENDER)",
    )
    parser.add_argument(
        "--max-mib",
        type=float,
        help="limite de descarga en MiB (def. 25 o $MAX_VIDEO_BYTES)",
    )
    parser.add_argument(
        "--out",
        default="descargas",
        help="directorio donde guardar el video descargado (def. descargas)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="segundos de espera tras conectar antes de enviar (def. 5)",
    )
    parser.add_argument(
        "--send-delay-ms",
        type=int,
        help=f"pausa entre tramas en ms (def. {DEFAULT_SEND_DELAY_MS} o $SEND_DELAY_MS)",
    )
    parser.add_argument(
        "--ack-timeout",
        type=float,
        default=DEFAULT_ACK_TIMEOUT,
        help=f"timeout de tdack por trama (def. {DEFAULT_ACK_TIMEOUT:g} s)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=f"reintentos por trama (def. {DEFAULT_RETRIES})",
    )
    parser.add_argument(
        "--frame-bytes",
        type=int,
        default=MAX_STANZA_BYTES,
        help=f"tamano maximo de trama (def. {MAX_STANZA_BYTES})",
    )
    parser.add_argument(
        "--resource",
        default="tds-lite-sender",
        help="recurso XMPP del emisor (def. tds-lite-sender)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="solo descarga/codifica y muestra el plan, sin conectar a ToDus",
    )
    parser.add_argument(
        "--insecure-tls",
        action="store_true",
        help="no verificar TLS (solo pruebas)",
    )
    return parser.parse_args(argv)


def resolve_source(args: argparse.Namespace) -> tuple[Path, int, str]:
    """Obtiene el fichero a enviar: descarga la URL o usa --file."""
    max_bytes = _env_int("MAX_VIDEO_BYTES", DEFAULT_MAX_BYTES)
    if args.max_mib is not None:
        max_bytes = int(args.max_mib * 1024 * 1024)

    if args.file:
        path = Path(args.file).expanduser().resolve()
        if not path.is_file():
            raise SystemExit(f"No existe el fichero: {path}")
        data = path.read_bytes()
        if len(data) > max_bytes:
            raise SystemExit(
                f"El fichero pesa {human_bytes(len(data))} y el limite es "
                f"{human_bytes(max_bytes)}"
            )
        import hashlib

        digest = hashlib.sha256(data).hexdigest()
        return path, len(data), digest

    url = args.url or _ask("Enlace del video")
    if not url:
        raise SystemExit("Falta el enlace del video.")
    cookies = args.cookies or os.environ.get("TDS_COOKIES_FILE")
    if not cookies and DEFAULT_COOKIES.is_file():
        cookies = str(DEFAULT_COOKIES)
    if cookies:
        print(f"Cookies: {cookies}")
    print(f"Descargando: {url}")
    path, size, digest = download_media(
        url,
        dest_dir=args.out,
        max_bytes=max_bytes,
        cookies=cookies,
        cookies_from_browser=args.cookies_from_browser,
    )
    return path, size, digest


def connect_with_retry(client: XmppClient, attempts: int = 3) -> None:
    """Conecta con reintentos: la resolucion DNS de ToDus es intermitente."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            client.connect()
            return
        except TodusError as exc:
            last_error = exc
            if attempt < attempts:
                print(
                    f"Conexion fallida (intento {attempt}/{attempts}): {exc}. "
                    "Reintentando...",
                    file=sys.stderr,
                )
                time.sleep(2 * attempt)
    assert last_error is not None
    raise last_error


def send_frames(
    frames,
    recipient_jid: str,
    sender_user: str,
    args: argparse.Namespace,
) -> None:
    send_delay = (
        args.send_delay_ms
        if args.send_delay_ms is not None
        else _env_int("SEND_DELAY_MS", DEFAULT_SEND_DELAY_MS)
    )
    client = XmppClient(
        username=sender_user,
        resource=args.resource,
        verify_tls=not args.insecure_tls,
        auth_url=os.environ.get("TODUS_AUTH_URL", AUTH_URL),
    )

    print(f"Conectando a ToDus como {sender_user}@im.todus.cu ...")
    connect_with_retry(client)
    print(f"Conectado como {client.jid}")
    print(f"Destino: {recipient_jid}")
    if args.delay > 0:
        print(
            f"Esperando {args.delay:g} s para que el receptor este escuchando "
            "(inicialo primero en el telefono)..."
        )
        time.sleep(args.delay)

    total = len(frames)
    started = time.monotonic()
    step = max(1, total // 100)
    sent = 0
    try:
        for index, frame in enumerate(frames):
            wire = frame.wire()
            if len(wire.encode("utf-8")) > args.frame_bytes:
                raise ProtocolError(f"trama {index} demasiado grande")

            ok = False
            last_error = ""
            for attempt in range(1, max(1, args.retries) + 1):
                try:
                    if not client.connected:
                        print("Conexion perdida; reconectando...", file=sys.stderr)
                        connect_with_retry(client, attempts=2)
                    message_id = client.send_message(recipient_jid, wire)
                    if client.wait_ack(message_id, args.ack_timeout):
                        ok = True
                        break
                    last_error = "sin tdack en el tiempo esperado"
                except TodusError as exc:
                    last_error = str(exc)
                if attempt < max(1, args.retries):
                    # Solo reconecta si la conexion esta caida. Si sigue viva,
                    # reenvia la misma trama (el receptor tolera duplicados).
                    if not client.connected:
                        try:
                            connect_with_retry(client, attempts=2)
                        except TodusError as exc:
                            last_error = str(exc)
                    time.sleep(0.3 * attempt)
            if not ok:
                raise TodusError(
                    f"trama {index + 1}/{total} no confirmada: {last_error}"
                )

            sent += 1
            if sent == total or sent % step == 0:
                elapsed = max(time.monotonic() - started, 1e-6)
                rate = sent / elapsed
                pct = sent * 100.0 / total
                line = (
                    f"\rEnviadas {sent}/{total} ({pct:5.1f}%) "
                    f"{rate:.1f} tramas/s"
                )
                print(line, end="", file=sys.stderr, flush=True)
            if send_delay > 0 and sent < total:
                time.sleep(send_delay / 1000.0)
    finally:
        print(file=sys.stderr)
        client.close()


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    recipient_raw = args.to or _ask(
        "Numero de telefono destino (sin 53 si es de 8 digitos)",
        DEFAULT_RECIPIENT,
    )
    try:
        recipient_jid = normalize_number(recipient_raw)
    except ProtocolError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    sender_raw = args.sender or os.environ.get("TODUS_SENDER", DEFAULT_SENDER)
    try:
        sender_jid = normalize_number(sender_raw)
    except ProtocolError as exc:
        print(f"Error en el numero emisor: {exc}", file=sys.stderr)
        return 2
    sender_user = local_part(sender_jid)

    if sender_jid == recipient_jid:
        print(
            "Aviso: emisor y destino son el mismo numero. Lo normal es usar "
            "dos cuentas distintas.",
            file=sys.stderr,
        )

    try:
        path, size, digest = resolve_source(args)
    except (DownloadError, OSError) as exc:
        print(f"Error de descarga: {exc}", file=sys.stderr)
        return 2

    print(f"Fichero: {path}")
    print(f"Tamano:  {size} bytes ({human_bytes(size)})")
    print(f"SHA-256: {digest}")

    try:
        data = path.read_bytes()
        frames, job_id, transfer_id = build_frames(
            data,
            max_frame_bytes=args.frame_bytes,
        )
    except (ProtocolError, OSError) as exc:
        print(f"Error de codificacion: {exc}", file=sys.stderr)
        return 3

    print(
        f"Codificado: {len(frames)} tramas "
        f"(job_id={job_id}, transfer_id={transfer_id})"
    )
    print(
        f"Cada trama <= {args.frame_bytes} bytes; "
        f"pausa {args.send_delay_ms if args.send_delay_ms is not None else _env_int('SEND_DELAY_MS', DEFAULT_SEND_DELAY_MS)} ms"
    )

    if args.dry_run:
        print("DRY-RUN: no se conecta a ToDus ni se envia nada.")
        for frame in frames[:3]:
            wire = frame.wire()
            print(
                f"  trama {frame.chunk_index}: {len(wire.encode('utf-8'))} bytes "
                f"UTF-8, {frame.payload_bytes} bytes de video"
            )
        if len(frames) > 3:
            print(f"  ... ({len(frames) - 3} tramas mas)")
        return 0

    try:
        send_frames(frames, recipient_jid, sender_user, args)
    except (TodusError, ProtocolError, KeyboardInterrupt) as exc:
        print(f"\nEnvio interrumpido/fallido: {exc}", file=sys.stderr)
        return 4

    print("\nENVIO COMPLETO")
    print(f"  job_id:  {job_id}")
    print(f"  tramas:  {len(frames)}")
    print(f"  tamano:  {size} bytes")
    print(f"  sha256:  {digest}")
    print("  El receptor debe reconstruir el fichero y mostrarlo en su terminal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
