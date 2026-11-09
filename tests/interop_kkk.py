#!/usr/bin/env python3
"""Interoperabilidad: tramas generadas por este proyecto -> receptor C++ kkk.

No usa red. Necesita el binario ``tds_receiver`` del kkk (o define
``TDS_RECEIVER_BIN``). Si no existe, termina con exito indicando "omitido".

    python3 tests/interop_kkk.py

Variable opcional: INTEROP_SIZE (bytes, por defecto 1 MiB).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Permite ejecutar desde la raiz del proyecto.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tds_lite.protocol import build_frames  # noqa: E402

DEFAULT_RECEIVER = "/root/kkk/build/client/tds_receiver"


def main() -> int:
    receiver = os.environ.get("TDS_RECEIVER_BIN", DEFAULT_RECEIVER)
    if not (Path(receiver).is_file() and os.access(receiver, os.X_OK)):
        print(f"OMITIDO: no existe el receptor C++ en {receiver}")
        print("Define TDS_RECEIVER_BIN para probar la interoperabilidad.")
        return 0

    size = int(os.environ.get("INTEROP_SIZE", 1024 * 1024))
    data = os.urandom(size)
    digest = hashlib.sha256(data).hexdigest()

    with tempfile.TemporaryDirectory(prefix="tds-interop-") as tmp:
        root = Path(tmp)
        frames_dir = root / "frames"
        frames_dir.mkdir()
        frames, job_id, transfer_id = build_frames(data)
        for frame in frames:
            (frames_dir / f"{frame.chunk_index:06d}.tds").write_text(
                frame.wire(), encoding="utf-8"
            )
        out = root / "recuperado.bin"
        cmd = [
            receiver,
            "--frames",
            str(frames_dir),
            "--job-id",
            job_id,
            "--transfer-id",
            transfer_id,
            "--size",
            str(size),
            "--sha256",
            digest,
            "--out",
            str(out),
        ]
        print("Ejecutando:", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout, end="")
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr, end="")
            print(f"FALLO: el receptor C++ devolvio {result.returncode}")
            return 1
        recovered = out.read_bytes()
        if recovered != data:
            print("FALLO: el fichero reconstruido no coincide byte a byte")
            return 1
        if hashlib.sha256(recovered).hexdigest() != digest:
            print("FALLO: SHA-256 distinto")
            return 1
        print(
            f"OK: {len(frames)} tramas, {size} bytes, SHA-256 identico "
            f"({digest})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
