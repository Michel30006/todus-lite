"""Pruebas offline del protocolo (sin red, sin ToDus)."""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from tds_lite.protocol import (
    MAX_STANZA_BYTES,
    Frame,
    ProtocolError,
    Reassembler,
    build_frames,
    decode_text,
    encode_bytes,
    guess_extension,
    normalize_number,
    parse_frame,
    restore_bytes,
)
from tds_lite.table_v1 import TABLE


class TestTable(unittest.TestCase):
    def test_table_integrity(self) -> None:
        self.assertEqual(len(TABLE), 256)
        self.assertEqual(len(set(TABLE)), 256)
        self.assertEqual(
            hashlib.sha256(TABLE.encode("utf-8")).hexdigest(),
            "c6cfa82beb0eabc11bcd1158264d3ec3de152469236f1280703c62cbfb84a26c",
        )
        self.assertNotIn("|", TABLE)
        for char in '<>&"\'':
            self.assertNotIn(char, TABLE)


class TestCodification(unittest.TestCase):
    def test_roundtrip_all_bytes(self) -> None:
        data = bytes(range(256))
        self.assertEqual(decode_text(encode_bytes(data)), data)

    def test_roundtrip_random(self) -> None:
        data = os.urandom(200_000)
        self.assertEqual(decode_text(encode_bytes(data)), data)

    def test_utf8_expansion(self) -> None:
        # La tabla v1 ocupa 1,6562 bytes UTF-8 por byte de entrada.
        data = bytes(range(256)) * 100
        encoded = encode_bytes(data).encode("utf-8")
        self.assertAlmostEqual(len(encoded) / len(data), 1.6562, places=3)


class TestNumbers(unittest.TestCase):
    def test_eight_digits(self) -> None:
        self.assertEqual(normalize_number("58548838"), "5358548838@im.todus.cu")

    def test_prefixed(self) -> None:
        self.assertEqual(normalize_number("5358548838"), "5358548838@im.todus.cu")

    def test_plus_and_spaces(self) -> None:
        self.assertEqual(normalize_number("+53 5854 8838"), "5358548838@im.todus.cu")

    def test_full_jid(self) -> None:
        self.assertEqual(
            normalize_number("5358548838@im.todus.cu"), "5358548838@im.todus.cu"
        )

    def test_invalid(self) -> None:
        for value in ("", "123", "blah", "5358548838@x@y"):
            with self.assertRaises(ProtocolError):
                normalize_number(value)


class TestFrames(unittest.TestCase):
    def _check_roundtrip(self, data: bytes) -> None:
        frames, job_id, transfer_id = build_frames(data)
        self.assertEqual(len(frames), frames[0].total_chunks)
        self.assertTrue(all(f.job_id == job_id for f in frames))
        self.assertTrue(all(f.transfer_id == transfer_id for f in frames))
        parsed = []
        for frame in frames:
            wire = frame.wire()
            self.assertLessEqual(len(wire.encode("utf-8")), MAX_STANZA_BYTES)
            parsed.append(parse_frame(wire))
        self.assertEqual(restore_bytes(parsed), data)

    def test_small(self) -> None:
        self._check_roundtrip(b"a")

    def test_1k(self) -> None:
        self._check_roundtrip(os.urandom(1024))

    def test_100k(self) -> None:
        self._check_roundtrip(os.urandom(100 * 1024))

    def test_1m(self) -> None:
        self._check_roundtrip(os.urandom(1024 * 1024))

    def test_crc_detects_corruption(self) -> None:
        frames, _, _ = build_frames(os.urandom(4096))
        wire = frames[0].wire()
        corrupted = wire[:-1] + ("!" if wire[-1] != "!" else "#")
        with self.assertRaises(ProtocolError):
            parse_frame(corrupted)

    def test_rejects_unknown_symbol(self) -> None:
        frame = Frame(
            job_id="a" * 16,
            transfer_id="b" * 16,
            chunk_index=0,
            total_chunks=1,
            encoding_version=1,
            payload="|",
        )
        with self.assertRaises(ProtocolError):
            parse_frame(frame.wire())

    def test_reassembler_out_of_order_and_duplicates(self) -> None:
        data = os.urandom(50_000)
        frames, job_id, transfer_id = build_frames(data)
        group = Reassembler(job_id=job_id, transfer_id=transfer_id)
        for frame in reversed(frames):
            group.add(frame)
        group.add(frames[0])  # duplicada
        self.assertTrue(group.complete)
        self.assertEqual(group.restore(), data)
        self.assertGreaterEqual(group.duplicates, 1)

    def test_empty_rejected(self) -> None:
        with self.assertRaises(ProtocolError):
            build_frames(b"")


class TestExtension(unittest.TestCase):
    def test_mp4(self) -> None:
        self.assertEqual(guess_extension(b"\x00\x00\x00\x18ftypisom"), ".mp4")

    def test_mov(self) -> None:
        self.assertEqual(guess_extension(b"\x00\x00\x00\x18ftypqt  "), ".mov")

    def test_unknown(self) -> None:
        self.assertEqual(guess_extension(b"hello"), ".bin")


if __name__ == "__main__":
    unittest.main()
