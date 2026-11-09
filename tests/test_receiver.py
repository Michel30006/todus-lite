"""Pruebas offline del receptor: alimenta tramas y comprueba el fichero."""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from receptor import Receiver
from tds_lite.protocol import build_frames
from tds_lite.todus import XmppMessage


def _message(body: str) -> XmppMessage:
    return XmppMessage("id", "a@b", "c@d", "chat", body, f"<m><b>{body}</b></m>")


class TestReceiver(unittest.TestCase):
    def test_rebuild_out_of_order(self) -> None:
        data = os.urandom(120_000)
        frames, _, _ = build_frames(data)
        with tempfile.TemporaryDirectory() as tmp:
            receiver = Receiver(Path(tmp), once=False, verbose=True)
            for frame in reversed(frames):
                receiver.on_message(_message(frame.wire()))
            self.assertEqual(receiver.ready.qsize(), 1)
            group = receiver.ready.get_nowait()
            path = receiver.write_group(group)
            self.assertIsNotNone(path)
            recovered = path.read_bytes()
            self.assertEqual(recovered, data)
            self.assertEqual(hashlib.sha256(recovered).hexdigest(),
                             hashlib.sha256(data).hexdigest())

    def test_ignores_non_tds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receiver = Receiver(Path(tmp), once=False, verbose=False)
            receiver.on_message(_message("hola"))
            self.assertEqual(receiver.accepted, 0)
            self.assertEqual(receiver.rejected, 0)
            self.assertEqual(receiver.ready.qsize(), 0)

    def test_rejects_corrupted_frame(self) -> None:
        data = os.urandom(4096)
        frames, _, _ = build_frames(data)
        wire = frames[0].wire()
        bad = wire[:-1] + ("!" if wire[-1] != "!" else "#")
        with tempfile.TemporaryDirectory() as tmp:
            receiver = Receiver(Path(tmp), once=False, verbose=False)
            receiver.on_message(_message(bad))
            self.assertEqual(receiver.accepted, 0)
            self.assertEqual(receiver.rejected, 1)


if __name__ == "__main__":
    unittest.main()
