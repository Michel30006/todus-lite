"""Pruebas offline del parser XMPP (sin red)."""

from __future__ import annotations

import unittest

from tds_lite.todus import (
    XmppMessage,
    _extract_body,
    _local_name,
    extract_stanzas,
    xml_attribute,
    xml_escape,
    xml_unescape,
)


class TestNames(unittest.TestCase):
    def test_aliases(self) -> None:
        self.assertEqual(_local_name("<m t='chat'>"), "message")
        self.assertEqual(_local_name("<b>"), "body")
        self.assertEqual(_local_name("<p/>"), "presence")
        self.assertEqual(_local_name("<tdack mi='x'/>"), "tdack")
        self.assertEqual(_local_name("<stream:features>"), "features")
        self.assertEqual(_local_name("<ok/>"), "success")

    def test_attributes(self) -> None:
        stanza = "<m t='chat' f='a@b' o='c@d' i='42'><b>hola</b></m>"
        self.assertEqual(xml_attribute(stanza, "type"), "chat")
        self.assertEqual(xml_attribute(stanza, "from"), "a@b")
        self.assertEqual(xml_attribute(stanza, "to"), "c@d")
        self.assertEqual(xml_attribute(stanza, "id"), "42")
        self.assertEqual(xml_attribute(stanza, "mi"), "")

    def test_escape(self) -> None:
        text = "TDS1|a|<b>&\"'"
        self.assertEqual(xml_unescape(xml_escape(text)), text)


class TestBody(unittest.TestCase):
    def test_full_body(self) -> None:
        stanza = "<message><body>TDS1|hola</body></message>"
        self.assertEqual(_extract_body(stanza), "TDS1|hola")

    def test_abbreviated_body(self) -> None:
        stanza = "<m t='chat'><b>TDS1|hola</b></m>"
        self.assertEqual(_extract_body(stanza), "TDS1|hola")

    def test_no_body(self) -> None:
        self.assertIsNone(_extract_body("<m t='chat'/>"))


class TestExtractStanzas(unittest.TestCase):
    def test_stream_and_feature(self) -> None:
        data = (
            "<?xml version='1.0'?>"
            "<stream:stream xmlns='jabber:client' "
            "xmlns:stream='http://etherx.jabber.org/streams'>"
            "<stream:features><mechanisms "
            "xmlns='urn:ietf:params:xml:ns:xmpp-sasl'>"
            "<mechanism>PLAIN</mechanism></mechanisms></stream:features>"
        )
        stanzas, rest, depth = extract_stanzas(data, 0)
        self.assertEqual(depth, 1)
        self.assertEqual(len(stanzas), 1)
        self.assertEqual(_local_name(stanzas[0]), "features")
        self.assertEqual(rest, "")

    def test_self_closing_success(self) -> None:
        stanzas, rest, depth = extract_stanzas("<ok/>", 1)
        self.assertEqual(depth, 1)
        self.assertEqual(len(stanzas), 1)
        self.assertEqual(_local_name(stanzas[0]), "success")
        self.assertEqual(rest, "")

    def test_partial_stanza_waits(self) -> None:
        stanzas, rest, depth = extract_stanzas("<m><b>TDS1|abc", 1)
        self.assertEqual(stanzas, [])
        self.assertEqual(rest, "<m><b>TDS1|abc")
        self.assertEqual(depth, 1)

    def test_complete_after_more_data(self) -> None:
        stanzas, rest, depth = extract_stanzas("<m><b>TDS1|abc", 1)
        stanzas, rest, depth = extract_stanzas(
            rest + "</b></m><tdack mi='1'/>", depth
        )
        self.assertEqual([_local_name(s) for s in stanzas], ["message", "tdack"])
        self.assertEqual(rest, "")
        self.assertEqual(_local_name(stanzas[0]), "message")
        self.assertEqual(_extract_body(stanzas[0]), "TDS1|abc")
        self.assertEqual(xml_attribute(stanzas[1], "mi"), "1")

    def test_stream_close(self) -> None:
        stanzas, rest, depth = extract_stanzas(
            "<stream:stream><m><b>x</b></m></stream:stream>", 0
        )
        self.assertEqual(depth, 0)
        self.assertEqual(len(stanzas), 1)
        self.assertEqual(rest, "")


class TestMessageDataclass(unittest.TestCase):
    def test_fields(self) -> None:
        msg = XmppMessage("1", "a", "b", "chat", "hola", "<m/>")
        self.assertEqual(msg.body, "hola")


if __name__ == "__main__":
    unittest.main()
