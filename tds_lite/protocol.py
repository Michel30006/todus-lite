"""Protocolo TDS1: codificacion, tramas, numeros y reensamblado.

Este modulo es una reimplementacion en Python puro del protocolo del proyecto
kkk (``shared/src/encoding.cpp``, ``framing.cpp`` y ``reassembler.cpp``). El
formato de trama es identico, de modo que el emisor de este proyecto tambien
puede ser recibido por el binario C++ ``tds_receiver`` del kkk:

    TDS1|<job_id>|<transfer_id>|<chunk_index>|<total_chunks>|<enc_ver>|<crc32>|<payload>

- ``job_id`` y ``transfer_id``: ``[A-Za-z0-9_-]``, 1..64 caracteres.
- ``payload``: texto usando la tabla v1 (no contiene ``|``).
- ``crc32``: CRC-32 (zlib/IEEE) del payload en UTF-8, 8 digitos hex.
- El tamano de la trama se mide en bytes UTF-8 y no debe superar
  ``MAX_STANZA_BYTES`` (8192 por defecto en ToDus).
"""

from __future__ import annotations

import re
import secrets
import zlib
from dataclasses import dataclass, field

from .table_v1 import DEC_TABLE, ENC_TABLE, TABLE

FRAME_MAGIC = "TDS1"
ENCODING_VERSION = 1
MAX_STANZA_BYTES = 8192
MAX_CHUNKS = 1_000_000
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TABLE_SET = frozenset(TABLE)
# Coincidencia en C de todo el payload: rechaza cualquier simbolo ajeno a v1.
_ALLOWED_RE = re.compile("[" + re.escape(TABLE) + "]+")

# Telefono cubano: 8 digitos locales (5XXXXXXX) o 10 con prefijo 53.
_DOMAIN = "im.todus.cu"


class ProtocolError(Exception):
    """Error de codificacion, trama o metadatos."""


# ---------------------------------------------------------------------------
# Codificacion byte <-> texto
# ---------------------------------------------------------------------------


def encode_bytes(data: bytes) -> str:
    """Convierte bytes en el texto de la tabla v1 (str)."""
    return data.decode("latin-1").translate(ENC_TABLE)


def decode_text(text: str) -> bytes:
    """Convierte texto de la tabla v1 en los bytes originales.

    Valida que todos los caracteres pertenecen a la tabla; de lo contrario un
    simbolo ajeno (p. ej. ``|``) se colaria como byte por latin-1.
    """
    if not text:
        return b""
    if _ALLOWED_RE.fullmatch(text) is None:
        for char in text:
            if char not in _TABLE_SET:
                raise ProtocolError(
                    f"simbolo U+{ord(char):04X} fuera de la tabla v1"
                )
        raise ProtocolError("texto con simbolos fuera de la tabla v1")
    return text.translate(DEC_TABLE).encode("latin-1")


def encoded_utf8(data: bytes) -> bytes:
    """Bytes UTF-8 del texto codificado (lo que viaja en el payload)."""
    return encode_bytes(data).encode("utf-8")


# ---------------------------------------------------------------------------
# Numeros / JID
# ---------------------------------------------------------------------------


def normalize_number(raw: str, domain: str = _DOMAIN) -> str:
    """Devuelve el JID de ToDus a partir de un numero o JID.

    Acepta:
      * ``58548838``        -> ``5358548838@im.todus.cu`` (antepone 53)
      * ``5358548838``      -> ``5358548838@im.todus.cu``
      * ``+53 58548838``    -> ``5358548838@im.todus.cu``
      * ``5358548838@im.todus.cu`` (JID completo, se respeta)

    No valida que la cuenta exista; solo normaliza el formato.
    """
    value = (raw or "").strip().replace(" ", "").replace("-", "")
    if not value:
        raise ProtocolError("numero vacio")
    if "@" in value:
        if value.count("@") != 1:
            raise ProtocolError(f"JID no valido: {raw!r}")
        local, dom = value.split("@", 1)
        if not local or not dom:
            raise ProtocolError(f"JID no valido: {raw!r}")
        return value
    if value.startswith("+"):
        value = value[1:]
    if not value.isdigit():
        raise ProtocolError(f"numero no valido: {raw!r}")
    if len(value) == 8:
        value = "53" + value
    if len(value) != 10 or not value.startswith("53"):
        raise ProtocolError(
            f"numero no valido: {raw!r} (usa 8 digitos, 53+8 digitos o un JID)"
        )
    return f"{value}@{domain}"


def local_part(jid: str) -> str:
    """Parte local de un JID (usuario XMPP)."""
    return jid.split("@", 1)[0]


def new_id() -> str:
    """Identificador corto valido para job_id/transfer_id."""
    return secrets.token_hex(8)  # 16 caracteres [0-9a-f]


# ---------------------------------------------------------------------------
# Tramas
# ---------------------------------------------------------------------------


@dataclass
class Frame:
    job_id: str
    transfer_id: str
    chunk_index: int
    total_chunks: int
    encoding_version: int
    payload: str  # texto de la tabla v1
    payload_crc32: int = 0

    @property
    def payload_bytes(self) -> int:
        """Bytes originales que representa esta trama."""
        return len(self.payload)

    def wire(self) -> str:
        crc = zlib.crc32(self.payload.encode("utf-8")) & 0xFFFFFFFF
        return (
            f"{FRAME_MAGIC}|{self.job_id}|{self.transfer_id}|"
            f"{self.chunk_index}|{self.total_chunks}|{self.encoding_version}|"
            f"{crc:08x}|{self.payload}"
        )


def conservative_header(job_id: str, transfer_id: str) -> int:
    """Cabecera contando 5 digitos para indice/total/version (como el kkk)."""
    return (
        len(FRAME_MAGIC)
        + 1
        + len(job_id)
        + 1
        + len(transfer_id)
        + 1
        + 5
        + 1
        + 5
        + 1
        + 5
        + 1
        + 8
        + 1
    )


def payload_budget(
    max_frame_bytes: int = MAX_STANZA_BYTES, job_id: str = "", transfer_id: str = ""
) -> int:
    budget = max_frame_bytes - conservative_header(job_id, transfer_id)
    if budget < 2:
        raise ProtocolError("presupuesto de payload insuficiente")
    return budget


def _split_utf8(raw: bytes, budget: int) -> list[tuple[int, int]]:
    """Divide bytes UTF-8 en trozos <= budget sin romper simbolos."""
    spans: list[tuple[int, int]] = []
    pos = 0
    size = len(raw)
    while pos < size:
        end = min(pos + budget, size)
        if end < size:
            # Si el corte cae en un byte de continuacion UTF-8, retrocede hasta
            # el inicio del simbolo (los simbolos v1 miden 1 o 2 bytes).
            while end > pos and (raw[end] & 0xC0) == 0x80:
                end -= 1
        if end <= pos:
            raise ProtocolError("no se pudo dividir el texto codificado")
        spans.append((pos, end))
        pos = end
    return spans


def build_frames(
    data: bytes,
    job_id: str | None = None,
    transfer_id: str | None = None,
    max_frame_bytes: int = MAX_STANZA_BYTES,
) -> tuple[list[Frame], str, str]:
    """Codifica ``data`` y construye todas las tramas.

    Devuelve ``(tramas, job_id, transfer_id)``. El texto completo se mantiene
    en memoria (un video de 25 MiB ocupa ~41 MiB de texto), igual que en kkk.
    """
    job_id = job_id or new_id()
    transfer_id = transfer_id or new_id()
    if not _ID_RE.match(job_id):
        raise ProtocolError(f"job_id invalido: {job_id!r}")
    if not _ID_RE.match(transfer_id):
        raise ProtocolError(f"transfer_id invalido: {transfer_id!r}")

    raw = encoded_utf8(data)
    budget = payload_budget(max_frame_bytes, job_id, transfer_id)
    spans = _split_utf8(raw, budget)
    total = len(spans)
    if total == 0:
        raise ProtocolError("no se generaron tramas (fichero vacio)")
    if total > MAX_CHUNKS:
        raise ProtocolError(f"demasiadas tramas: {total}")

    frames: list[Frame] = []
    for index, (start, end) in enumerate(spans):
        chunk = raw[start:end]
        try:
            payload = chunk.decode("utf-8")
        except UnicodeDecodeError as exc:  # no deberia ocurrir
            raise ProtocolError(f"trama {index} no es UTF-8 valido: {exc}") from exc
        frame = Frame(
            job_id=job_id,
            transfer_id=transfer_id,
            chunk_index=index,
            total_chunks=total,
            encoding_version=ENCODING_VERSION,
            payload=payload,
        )
        wire = frame.wire()
        if len(wire.encode("utf-8")) > max_frame_bytes:
            raise ProtocolError(
                f"trama {index} supera {max_frame_bytes} bytes "
                f"({len(wire.encode('utf-8'))})"
            )
        frames.append(frame)
    return frames, job_id, transfer_id


def parse_frame(wire: str) -> Frame:
    """Valida y parsea una trama TDS1 completa."""
    fields = wire.split("|", 7)
    if len(fields) != 8:
        raise ProtocolError("trama truncada: faltan campos")
    magic, job_id, transfer_id, idx, total, ver, crc_hex, payload = fields
    if magic != FRAME_MAGIC:
        raise ProtocolError("magic de trama desconocido")
    if not _ID_RE.match(job_id):
        raise ProtocolError("job_id invalido")
    if not _ID_RE.match(transfer_id):
        raise ProtocolError("transfer_id invalido")
    try:
        chunk_index = int(idx)
        total_chunks = int(total)
        encoding_version = int(ver)
        expected_crc = int(crc_hex, 16)
    except ValueError as exc:
        raise ProtocolError(f"campos numericos invalidos: {exc}") from exc
    if not (0 <= chunk_index < total_chunks <= MAX_CHUNKS):
        raise ProtocolError("indices de trama fuera de rango")
    if not (1 <= encoding_version <= 65535):
        raise ProtocolError("version de codificacion invalida")
    if not payload:
        raise ProtocolError("payload vacio")
    # Verifica CRC antes de decodificar.
    actual_crc = zlib.crc32(payload.encode("utf-8")) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        raise ProtocolError("crc de payload no coincide")
    # Verifica que todos los simbolos pertenecen a la tabla v1.
    decode_text(payload)
    return Frame(
        job_id=job_id,
        transfer_id=transfer_id,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        encoding_version=encoding_version,
        payload=payload,
        payload_crc32=expected_crc,
    )


def restore_bytes(frames: list[Frame]) -> bytes:
    """Reensambla y decodifica una lista de tramas completas."""
    if not frames:
        raise ProtocolError("no hay tramas")
    total = frames[0].total_chunks
    by_index: dict[int, Frame] = {}
    for frame in frames:
        if frame.total_chunks != total:
            raise ProtocolError("total_chunks incoherente")
        by_index[frame.chunk_index] = frame
    if len(by_index) != total:
        missing = sorted(set(range(total)) - set(by_index))
        raise ProtocolError(
            f"faltan {len(missing)} tramas (primera: {missing[0] if missing else '?'})"
        )
    return b"".join(decode_text(by_index[i].payload) for i in range(total))


# ---------------------------------------------------------------------------
# Reensamblador incremental (receptor)
# ---------------------------------------------------------------------------


@dataclass
class Reassembler:
    """Acumula tramas de un grupo (job_id, transfer_id) hasta completarlo."""

    job_id: str
    transfer_id: str
    total_chunks: int = 0
    parts: dict[int, bytes] = field(default_factory=dict)
    duplicates: int = 0
    rejected: int = 0
    out_of_order: int = 0
    expected_next: int = 0

    def add(self, frame: Frame) -> bool:
        """Anade una trama. Devuelve True si el grupo queda completo."""
        if self.total_chunks == 0:
            self.total_chunks = frame.total_chunks
        elif frame.total_chunks != self.total_chunks:
            self.rejected += 1
            raise ProtocolError("total_chunks incoherente con las tramas previas")
        if frame.chunk_index >= self.total_chunks:
            self.rejected += 1
            raise ProtocolError("indice fuera de rango")
        if frame.chunk_index in self.parts:
            self.duplicates += 1
            return self.complete
        if frame.chunk_index != self.expected_next:
            self.out_of_order += 1
        self.parts[frame.chunk_index] = decode_text(frame.payload)
        self.expected_next += 1
        return self.complete

    @property
    def complete(self) -> bool:
        return self.total_chunks > 0 and len(self.parts) == self.total_chunks

    @property
    def received(self) -> int:
        return len(self.parts)

    def missing(self) -> list[int]:
        return [i for i in range(self.total_chunks) if i not in self.parts]

    def restore(self) -> bytes:
        if not self.complete:
            gaps = self.missing()
            raise ProtocolError(
                f"faltan {len(gaps)} tramas (primera: {gaps[0] if gaps else '?'})"
            )
        return b"".join(self.parts[i] for i in range(self.total_chunks))


# ---------------------------------------------------------------------------
# Utilidades de fichero
# ---------------------------------------------------------------------------


def guess_extension(data: bytes) -> str:
    """Extension probable segun los primeros bytes (igual que kkk)."""
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return ".mov" if data[8:12] == b"qt  " else ".mp4"
    if data[:4] == b"RIFF" and data[8:12] == b"AVI ":
        return ".avi"
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return ".mkv"
    if data[:4] == b"\x00\x00\x01\xba":
        return ".mpg"
    return ".bin"
