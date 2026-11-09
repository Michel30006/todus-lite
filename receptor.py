#!/usr/bin/env python3
"""Receptor ligero: escucha tramas TDS1 por ToDus y reconstruye el fichero.

Pensado para ejecutarse en el telefono (Termux) o en cualquier equipo:

    python3 receptor.py

Pide el numero de telefono del receptor (por defecto 58548838). Si escribes
solo 8 digitos, antepone automaticamente el 53. Tambien acepta 53+8 digitos o
un JID completo.

Debe iniciarse ANTES del emisor. Se queda escuchando y reconstruye cada
fichero que llegue, escribiendolo en /sdcard/Download si existe (o en
recibidos/ si no).

Tambien es compatible con el receptor C++ del proyecto kkk: las tramas son
identicas. Si prefieres el binario verificado, usa receptor.sh.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import queue
import signal
import sys
import threading
import time
from pathlib import Path

from tds_lite.protocol import (
    ProtocolError,
    Reassembler,
    guess_extension,
    local_part,
    normalize_number,
    parse_frame,
)
from tds_lite.todus import AUTH_URL, TodusError, XmppClient, XmppMessage

DEFAULT_NUMBER = "58548838"


def default_output_dir() -> Path:
    for candidate in ("/sdcard/Download", "/storage/emulated/0/Download"):
        if os.path.isdir(candidate):
            return Path(candidate)
    return Path(__file__).resolve().parent / "recibidos"


def _ask(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{text}{suffix}: ").strip()
    except EOFError:
        raise SystemExit("Entrada cancelada.")
    return answer or default


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Escucha ToDus y reconstruye ficheros enviados con TDS1."
    )
    parser.add_argument("--number", help=f"numero receptor (def. {DEFAULT_NUMBER})")
    parser.add_argument(
        "--out",
        help="directorio de salida (def. /sdcard/Download o recibidos/)",
    )
    parser.add_argument(
        "--resource", default="tds-lite-receiver", help="recurso XMPP"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="salir tras reconstruir el primer fichero",
    )
    parser.add_argument(
        "--insecure-tls", action="store_true", help="no verificar TLS (pruebas)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="mostrar errores de tramas rechazadas",
    )
    return parser.parse_args(argv)


class Receiver:
    def __init__(self, out_dir: Path, once: bool, verbose: bool) -> None:
        self.out_dir = out_dir
        self.once = once
        self.verbose = verbose
        self.lock = threading.Lock()
        self.groups: dict[tuple[str, str], Reassembler] = {}
        self.ready: queue.Queue[Reassembler] = queue.Queue()
        self.stop = threading.Event()
        self.accepted = 0
        self.rejected = 0
        self.written = 0

    # -- callback del hilo lector XMPP ------------------------------------
    def on_message(self, message: XmppMessage) -> None:
        body = message.body
        if not body.startswith("TDS1|"):
            return
        try:
            frame = parse_frame(body)
        except ProtocolError as exc:
            with self.lock:
                self.rejected += 1
                rejected = self.rejected
            if self.verbose and rejected <= 5:
                print(f"\nTrama rechazada: {exc}", file=sys.stderr)
            return

        key = (frame.job_id, frame.transfer_id)
        with self.lock:
            group = self.groups.get(key)
            if group is None:
                group = Reassembler(
                    job_id=frame.job_id, transfer_id=frame.transfer_id
                )
                self.groups[key] = group
            try:
                complete = group.add(frame)
            except ProtocolError as exc:
                self.rejected += 1
                if self.verbose:
                    print(f"\nTrama rechazada: {exc}", file=sys.stderr)
                return
            self.accepted += 1
            if complete:
                self.groups.pop(key, None)
                self.ready.put(group)

    # -- escritura --------------------------------------------------------
    def write_group(self, group: Reassembler) -> Path | None:
        try:
            data = group.restore()
        except ProtocolError as exc:
            print(f"\nError al reconstruir {group.job_id}: {exc}", file=sys.stderr)
            return None

        self.out_dir.mkdir(parents=True, exist_ok=True)
        ext = guess_extension(data)
        target = self.out_dir / f"{group.job_id}{ext}"
        counter = 1
        while target.exists():
            target = self.out_dir / f"{group.job_id}_{counter}{ext}"
            counter += 1
        partial = target.with_suffix(target.suffix + ".part")
        partial.write_bytes(data)
        partial.replace(target)

        digest = hashlib.sha256(data).hexdigest()
        self.written += 1
        print(
            "\nARCHIVO RECIBIDO Y RECONSTRUIDO\n"
            f"  job:     {group.job_id}\n"
            f"  fichero: {target}\n"
            f"  tamano:  {len(data)} bytes\n"
            f"  sha256:  {digest}\n"
            f"  tramas:  {group.received}/{group.total_chunks}"
            + (
                f" (duplicadas: {group.duplicates}, desorden: {group.out_of_order})"
                if group.duplicates or group.out_of_order
                else ""
            )
        )
        return target

    # -- bucle principal --------------------------------------------------
    def run(self, number: str, args: argparse.Namespace) -> int:
        try:
            jid = normalize_number(number)
        except ProtocolError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        user = local_part(jid)

        def handle_signal(_signum, _frame):
            self.stop.set()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        print("Receptor ToDus ligero")
        print(f"  cuenta: {user}@im.todus.cu")
        print(f"  salida: {self.out_dir}")
        print("  IMPORTANTE: deja este receptor escuchando ANTES de lanzar enviar.py")
        print("  (Ctrl-C para detener)")
        print()

        backoff = 1
        announced: set[tuple[str, str]] = set()
        last_pct: dict[tuple[str, str], int] = {}

        while not self.stop.is_set():
            client = XmppClient(
                username=user,
                resource=args.resource,
                verify_tls=not args.insecure_tls,
                auth_url=os.environ.get("TODUS_AUTH_URL", AUTH_URL),
                on_message=self.on_message,
            )
            try:
                print(f"Conectando a ToDus como {user}@im.todus.cu ...")
                client.connect()
                print(f"Conectado como {client.jid}")
                print("LISTO. Esperando tramas TDS1...\n")
                backoff = 1

                while not self.stop.is_set() and client.connected:
                    # Escribe los grupos completos (fuera del hilo lector).
                    while True:
                        try:
                            group = self.ready.get_nowait()
                        except queue.Empty:
                            break
                        self.write_group(group)
                        if self.once:
                            self.stop.set()
                            break

                    # Progreso de los grupos activos.
                    with self.lock:
                        snapshot = [
                            (key, g.received, g.total_chunks)
                            for key, g in self.groups.items()
                        ]
                    for key, received, total in snapshot:
                        if key not in announced:
                            announced.add(key)
                            print(f"Recibiendo {key[0]} ({total} tramas)...")
                        if total:
                            pct = int(received * 100 / total)
                            if pct >= last_pct.get(key, -1) + 10:
                                last_pct[key] = pct
                                print(f"  {key[0]}: {received}/{total} ({pct}%)")

                    time.sleep(0.5)
            except TodusError as exc:
                if not self.stop.is_set():
                    print(f"\nError de conexion: {exc}", file=sys.stderr)
            except Exception as exc:  # noqa: BLE001 - no tumbar el receptor
                if not self.stop.is_set():
                    print(f"\nError inesperado: {exc}", file=sys.stderr)
            finally:
                client.close()

            if self.stop.is_set():
                break
            print(f"Reintentando en {backoff} s...", file=sys.stderr)
            for _ in range(backoff * 2):
                if self.stop.is_set():
                    break
                time.sleep(0.5)
            backoff = min(backoff * 2, 15)

        print(
            f"\nReceptor detenido. Tramas aceptadas: {self.accepted}, "
            f"rechazadas: {self.rejected}, ficheros: {self.written}"
        )
        return 0


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    number = args.number or _ask(
        "Numero de telefono de este receptor (8 digitos o 53+8)", DEFAULT_NUMBER
    )
    out_dir = Path(args.out).expanduser() if args.out else default_output_dir()
    receiver = Receiver(out_dir=out_dir, once=args.once, verbose=args.verbose)
    return receiver.run(number, args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
