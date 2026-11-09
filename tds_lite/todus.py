"""Cliente minimo de ToDus (autenticacion + XMPP) en Python puro.

Protocolo reconstruido/reutilizado de ``kkk/shared/src/xmpp.cpp``:

1. ``POST https://auth.todus.cu/v2/auth/token`` con un cuerpo protobuf:
      field 1 (string) = usuario  -> "53" + telefono
      field 2 (string) = password -> opcional (no hace falta)
      field 3 (string) = version  -> "2.1.2"
   La respuesta trae en el field 2 el JWT que se usa como contrasena XMPP.

2. TLS directo a ``im.todus.cu:5222`` (no STARTTLS).
3. ``<stream:stream>``, SASL PLAIN con usuario y JWT, reapertura del stream y
   bind clasico de recurso.
4. Presencia con prioridad 10 para que ToDus entregue los mensajes a este
   recurso y no a la app movil.
5. Los mensajes son ``<message type='chat'><body>...</body></message>`` y el
   servidor acusa con ``<tdack mi='...'/>``.

No usa dependencias externas: socket, ssl, base64, urllib y threading.
"""

from __future__ import annotations

import base64
import codecs
import html
import re
import socket
import ssl
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .protocol import MAX_STANZA_BYTES

AUTH_URL = "https://auth.todus.cu/v2/auth/token"
TODUS_HOST = "im.todus.cu"
TODUS_PORT = 5222
TODUS_VERSION = "2.1.2"

NS_CLIENT = "jabber:client"
NS_STREAM = "http://etherx.jabber.org/streams"
NS_SASL = "urn:ietf:params:xml:ns:xmpp-sasl"
NS_BIND = "urn:ietf:params:xml:ns:xmpp-bind"
NS_SESSION = "urn:ietf:params:xml:ns:xmpp-session"


class TodusError(Exception):
    """Error de autenticacion, conexion o protocolo XMPP."""


# ---------------------------------------------------------------------------
# Protobuf minimo para /v2/auth/token
# ---------------------------------------------------------------------------


def _varint(value: int) -> bytes:
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _pb_string(field: int, value: str) -> bytes:
    raw = value.encode("utf-8")
    return _varint((field << 3) | 2) + _varint(len(raw)) + raw


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7
        if shift > 63:
            raise TodusError("varint demasiado largo")
    raise TodusError("varint truncado")


def encode_auth_request(username: str, password: str = "") -> bytes:
    body = _pb_string(1, username)
    if password:
        body += _pb_string(2, password)
    body += _pb_string(3, TODUS_VERSION)
    return body


def decode_auth_response(data: bytes) -> str:
    token = ""
    pos = 0
    while pos < len(data):
        key, pos = _read_varint(data, pos)
        field = key >> 3
        wire = key & 0x07
        if wire == 0:
            _, pos = _read_varint(data, pos)
        elif wire == 2:
            length, pos = _read_varint(data, pos)
            if pos + length > len(data):
                raise TodusError("campo protobuf truncado")
            value = data[pos : pos + length]
            pos += length
            if field == 2:
                token = value.decode("utf-8", "replace")
        elif wire == 1:
            pos += 8
        elif wire == 5:
            pos += 4
        else:
            raise TodusError(f"wire type no soportado: {wire}")
    if not token:
        raise TodusError("la respuesta de auth/token no contiene tokenString")
    return token


def fetch_token(
    username: str,
    password: str = "",
    auth_url: str = AUTH_URL,
    timeout: float = 25.0,
    attempts: int = 4,
) -> str:
    """Obtiene un JWT de ToDus. Con solo el numero suele bastar.

    La resolucion DNS de ToDus puede fallar de forma intermitente; se
    reintenta ante errores de red (no ante un HTTP de autenticacion).
    """
    body = encode_auth_request(username, password)
    request = Request(
        auth_url,
        data=body,
        headers={
            "Content-Type": "application/x-protobuf",
            "User-Agent": f"ToDus/{TODUS_VERSION}",
        },
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                data = response.read()
            return decode_auth_response(data)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise TodusError(f"auth/token HTTP {exc.code}: {detail}") from exc
        except (URLError, OSError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(1.5 * attempt)
                continue
    reason = getattr(last_error, "reason", last_error)
    raise TodusError(f"auth/token no accesible: {reason}") from last_error


# ---------------------------------------------------------------------------
# Utilidades XML / stanza
# ---------------------------------------------------------------------------

_ELEMENT_ALIASES = {
    "m": "message",
    "p": "presence",
    "b": "body",
    "es": "mechanisms",
    "e": "mechanism",
    "b1": "bind",
    "bind": "bind",
    "s1": "session",
    "ok": "success",
}
_ATTRIBUTE_ALIASES = {
    "t": "type",
    "i": "id",
    "f": "from",
    "o": "to",
}
_ATTR_RE = re.compile(
    r"([A-Za-z_:][A-Za-z0-9_:.\-]*)\s*=\s*(['\"])(.*?)\2", re.DOTALL
)


def _normalize_element(name: str) -> str:
    key = name.lower()
    return _ELEMENT_ALIASES.get(key, key)


def _normalize_attribute(name: str) -> str:
    key = name.lower()
    return _ATTRIBUTE_ALIASES.get(key, key)


def xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def xml_unescape(text: str) -> str:
    try:
        return html.unescape(text)
    except Exception:
        return text


def _local_name(tag: str) -> str:
    text = tag.lstrip()
    if text.startswith("</"):
        text = text[2:]
    elif text.startswith("<"):
        text = text[1:]
    end = 0
    while end < len(text) and not text[end].isspace() and text[end] not in ">/":
        end += 1
    name = text[:end]
    if ":" in name:
        name = name.rsplit(":", 1)[1]
    return _normalize_element(name)


def _tag_end(text: str, pos: int) -> int:
    """Posicion justo despues del '>' que cierra la etiqueta en ``pos``."""
    in_single = False
    in_double = False
    i = pos + 1
    while i < len(text):
        char = text[i]
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == ">" and not in_single and not in_double:
            return i + 1
        i += 1
    return -1


def _open_tag(stanza: str) -> str:
    end = _tag_end(stanza, 0)
    return stanza[:end] if end > 0 else stanza


def xml_attribute(stanza: str, name: str) -> str:
    wanted = _normalize_attribute(name)
    tag = _open_tag(stanza)
    for match in _ATTR_RE.finditer(tag):
        if _normalize_attribute(match.group(1)) == wanted:
            return xml_unescape(match.group(3))
    return ""


def _extract_body(stanza: str) -> str | None:
    pos = 0
    while True:
        lt = stanza.find("<", pos)
        if lt < 0:
            return None
        end = _tag_end(stanza, lt)
        if end < 0:
            return None
        tag = stanza[lt:end]
        name = _local_name(tag)
        closing = tag.startswith("</")
        self_closing = tag.rstrip().endswith("/>")
        if name == "body" and not closing and not self_closing:
            close = stanza.find("</", end)
            if close < 0:
                return None
            return xml_unescape(stanza[end:close])
        pos = end


def extract_stanzas(buffer: str, depth: int) -> tuple[list[str], str, int]:
    """Extrae stanzas completas del buffer de un stream XMPP.

    Devuelve ``(stanzas, buffer_restante, depth)``. ``depth`` es 0 fuera del
    ``<stream:stream>`` y 1 dentro. Es un port de ``extract_xmpp_stanzas``.
    """
    out: list[str] = []
    pos = 0
    size = len(buffer)
    while pos < size:
        lt = buffer.find("<", pos)
        if lt < 0:
            pos = size
            break
        if buffer.startswith("<?", lt):
            end = buffer.find("?>", lt)
            if end < 0:
                break
            pos = end + 2
            continue
        if buffer.startswith("<!--", lt):
            end = buffer.find("-->", lt)
            if end < 0:
                break
            pos = end + 3
            continue
        if buffer.startswith("<![CDATA[", lt):
            end = buffer.find("]]>", lt)
            if end < 0:
                break
            pos = end + 3
            continue

        end = _tag_end(buffer, lt)
        if end < 0:
            break
        tag = buffer[lt:end]
        closing = tag.startswith("</")
        self_closing = tag.rstrip().endswith("/>")
        name = _local_name(tag)

        if depth == 0:
            if not closing and name == "stream":
                depth = 1
                pos = end
                continue
            pos = end
            continue
        if closing and name == "stream":
            depth = 0
            pos = end
            continue
        if closing:
            pos = end
            continue
        if self_closing:
            out.append(tag)
            pos = end
            continue

        # Busca el cierre de este elemento respetando anidamiento.
        nested = 0
        scan = end
        close_end = -1
        while scan < size:
            nxt = buffer.find("<", scan)
            if nxt < 0:
                break
            if buffer.startswith("<!--", nxt):
                comment_end = buffer.find("-->", nxt)
                if comment_end < 0:
                    break
                scan = comment_end + 3
                continue
            if buffer.startswith("<![CDATA[", nxt):
                cdata_end = buffer.find("]]>", nxt)
                if cdata_end < 0:
                    break
                scan = cdata_end + 3
                continue
            inner_end = _tag_end(buffer, nxt)
            if inner_end < 0:
                break
            inner = buffer[nxt:inner_end]
            inner_closing = inner.startswith("</")
            inner_self = inner.rstrip().endswith("/>")
            if inner_closing:
                if nested == 0:
                    close_end = inner_end
                    break
                nested -= 1
            elif not inner_self:
                nested += 1
            scan = inner_end
        if close_end < 0:
            break
        out.append(buffer[lt:close_end])
        pos = close_end

    return out, buffer[pos:], depth


# ---------------------------------------------------------------------------
# Cliente XMPP
# ---------------------------------------------------------------------------


@dataclass
class XmppMessage:
    id: str
    sender: str
    to: str
    type: str
    body: str
    raw: str


class XmppClient:
    """Cliente XMPP minimo para enviar/recibir tramas TDS1 por ToDus."""

    def __init__(
        self,
        username: str,
        token: str | None = None,
        password: str = "",
        host: str = TODUS_HOST,
        port: int = TODUS_PORT,
        resource: str = "tds-lite",
        verify_tls: bool = True,
        timeout: float = 25.0,
        auth_url: str = AUTH_URL,
        on_message: Callable[[XmppMessage], None] | None = None,
    ) -> None:
        self.username = username
        self.token = token or ""
        self.password = password
        self.host = host
        self.port = port
        self.resource = resource
        self.verify_tls = verify_tls
        self.timeout = timeout
        self.auth_url = auth_url
        self.on_message = on_message

        self.jid = ""
        self._sock: ssl.SSLSocket | None = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._ack_cv = threading.Condition(self._state_lock)
        self._acks: set[str] = set()
        self._buffer = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._depth = 0
        self._counter = 0
        self._last_activity = 0.0
        # Cache de la IP resuelta: si el DNS falla de forma transitoria,
        # reconectar usando la ultima IP conocida (TLS sigue verificando el
        # certificado contra self.host).
        self._cached_ip: str | None = None

    # -- estado -----------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    # -- conexion ---------------------------------------------------------
    def connect(self, token: str | None = None) -> None:
        """Conecta, autentica y hace bind. Reintenta desde cero si se llama."""
        self.close()
        if token:
            self.token = token
        if not self.token:
            self.token = fetch_token(
                self.username,
                self.password,
                auth_url=self.auth_url,
                timeout=self.timeout,
            )

        self._stop.clear()
        self._connected.clear()
        self._buffer = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._depth = 0
        with self._state_lock:
            self._acks.clear()

        self._open_socket()
        try:
            self._send_stream(with_declaration=True)
            self._wait_features()
            self._authenticate()
            self._send_stream(with_declaration=False)
            self._wait_features()
            self._bind()
            self._send_raw(
                f"<session xmlns='{NS_SESSION}'/>", check=False
            )
            self._send_raw("<presence><priority>10</priority></presence>", check=False)
        except Exception:
            self.close()
            raise

        self._connected.set()
        self._reader = threading.Thread(
            target=self._reader_loop, name="todus-xmpp-reader", daemon=True
        )
        self._reader.start()

    def _resolve(self) -> str:
        """Resuelve el host con reintentos y cache de la ultima IP."""
        errors: list[str] = []
        for attempt in range(1, 4):
            try:
                infos = socket.getaddrinfo(
                    self.host, self.port, type=socket.SOCK_STREAM
                )
                if infos:
                    self._cached_ip = infos[0][4][0]
                    return self._cached_ip
            except socket.gaierror as exc:
                errors.append(str(exc))
                time.sleep(0.5 * attempt)
        if self._cached_ip:
            print(
                f"Aviso: DNS fallo ({errors[-1] if errors else '?'}); "
                f"usando IP cache {self._cached_ip}",
                file=sys.stderr,
            )
            return self._cached_ip
        raise TodusError(
            f"no se pudo resolver {self.host}: "
            f"{errors[-1] if errors else 'sin respuesta DNS'}"
        )

    def _open_socket(self) -> None:
        context = ssl.create_default_context()
        if not self.verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        last_error: Exception | None = None
        for attempt in range(1, 3):
            ip = self._resolve()
            try:
                raw = socket.create_connection((ip, self.port), timeout=self.timeout)
                raw.settimeout(self.timeout)
                self._sock = context.wrap_socket(raw, server_hostname=self.host)
                return
            except (OSError, ssl.SSLError) as exc:
                last_error = exc
                # La IP cacheada pudo quedar obsoleta: fuerza nueva resolucion.
                self._cached_ip = None
                if attempt < 2:
                    time.sleep(1.0)
        raise TodusError(
            f"conexion TLS a {self.host}:{self.port} fallo: {last_error}"
        ) from last_error

    def close(self) -> None:
        self._stop.set()
        self._connected.clear()
        with self._ack_cv:
            self._ack_cv.notify_all()
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        reader = self._reader
        self._reader = None
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=2.0)

    # -- E/S --------------------------------------------------------------
    def _send_raw(self, data: str, check: bool = True) -> None:
        sock = self._sock
        if sock is None:
            if check:
                raise TodusError("sin conexion XMPP")
            return
        payload = data.encode("utf-8")
        with self._send_lock:
            try:
                sock.sendall(payload)
            except (OSError, ssl.SSLError, AttributeError) as exc:
                raise TodusError(f"fallo escribiendo en XMPP: {exc}") from exc
        self._last_activity = time.monotonic()

    def _recv(self, timeout: float) -> bool:
        """Lee algo del socket. True si hubo datos, False si timeout."""
        sock = self._sock
        if sock is None:
            raise TodusError("sin conexion XMPP")
        try:
            sock.settimeout(timeout)
            data = sock.recv(65536)
        except (socket.timeout, TimeoutError):
            return False
        except (OSError, ssl.SSLError, AttributeError) as exc:
            raise TodusError(f"conexion XMPP perdida: {exc}") from exc
        if not data:
            raise TodusError("el servidor cerro la conexion XMPP")
        try:
            self._buffer += self._decoder.decode(data)
        except UnicodeDecodeError as exc:
            raise TodusError(f"UTF-8 invalido en el stream XMPP: {exc}") from exc
        self._last_activity = time.monotonic()
        return True

    def _extract(self) -> list[str]:
        stanzas, self._buffer, self._depth = extract_stanzas(
            self._buffer, self._depth
        )
        return stanzas

    def _wait_for(
        self,
        names: set[str],
        timeout: float | None = None,
        reset_depth: bool = False,
    ) -> str:
        if reset_depth:
            self._depth = 0
        deadline = time.monotonic() + (timeout if timeout is not None else self.timeout)
        while time.monotonic() < deadline:
            for stanza in self._extract():
                if _local_name(stanza) in names:
                    return stanza
            self._recv(0.5)
        raise TodusError(f"tiempo agotado esperando {sorted(names)}")

    # -- handshake --------------------------------------------------------
    def _send_stream(self, with_declaration: bool) -> None:
        header = ""
        if with_declaration:
            header += "<?xml version='1.0'?>"
        header += (
            f"<stream:stream to='{xml_escape(self.host)}' "
            f"xmlns='{NS_CLIENT}' xmlns:stream='{NS_STREAM}' version='1.0'>"
        )
        self._send_raw(header)
        # Pequena pausa como en kkk: deja que el servidor responda.
        time.sleep(0.1)

    def _wait_features(self) -> str:
        return self._wait_for({"features"}, reset_depth=True)

    def _authenticate(self) -> None:
        raw = "\0" + self.username + "\0" + self.token
        payload = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        self._send_raw(
            f"<auth xmlns='{NS_SASL}' mechanism='PLAIN'>{payload}</auth>"
        )
        stanza = self._wait_for({"success", "failure"})
        name = _local_name(stanza)
        if name == "failure":
            raise TodusError(f"SASL PLAIN rechazado: {stanza[:200]}")

    def _bind(self) -> None:
        self._counter += 1
        iq_id = f"bind_{self._counter}"
        self._send_raw(
            f"<iq xmlns='{NS_CLIENT}' type='set' id='{iq_id}'>"
            f"<bind xmlns='{NS_BIND}'><resource>{xml_escape(self.resource)}</resource>"
            f"</bind></iq>"
        )
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            for stanza in self._extract():
                if _local_name(stanza) != "iq":
                    continue
                if xml_attribute(stanza, "id") != iq_id:
                    continue
                if xml_attribute(stanza, "type") == "error":
                    raise TodusError("el servidor rechazo el bind")
                match = re.search(r"<jid[^>]*>(.*?)</jid>", stanza, re.DOTALL)
                if match:
                    self.jid = xml_unescape(match.group(1))
                if not self.jid:
                    self.jid = (
                        f"{self.username}@{self.host}/{self.resource}"
                    )
                return
            self._recv(0.5)
        raise TodusError("tiempo agotado esperando el bind")

    # -- mensajes ---------------------------------------------------------
    def send_message(self, to: str, body: str) -> str:
        self._counter += 1
        message_id = f"tds-{self._counter}-{int(time.time() * 1000)}"
        stanza = (
            f"<message xmlns='{NS_CLIENT}' type='chat' to='{xml_escape(to)}' "
            f"id='{message_id}'><body>{xml_escape(body)}</body></message>"
        )
        self._send_raw(stanza)
        return message_id

    def wait_ack(self, message_id: str, timeout: float = 15.0) -> bool:
        """Espera el ``<tdack mi='...'>`` del servidor para ese mensaje."""
        deadline = time.monotonic() + timeout
        with self._ack_cv:
            while message_id not in self._acks:
                if not self._connected.is_set():
                    return False
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._ack_cv.wait(remaining)
            self._acks.discard(message_id)
            return True

    # -- bucle lector -----------------------------------------------------
    def _reader_loop(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    got = self._recv(1.0)
                except TodusError:
                    break
                if not got:
                    # Keepalive: un espacio cada 60 s sin actividad.
                    if time.monotonic() - self._last_activity > 60:
                        try:
                            self._send_raw(" ", check=False)
                        except TodusError:
                            break
                    continue
                try:
                    stanzas = self._extract()
                except Exception:
                    break
                for stanza in stanzas:
                    if self._dispatch(stanza):
                        return
        finally:
            self._connected.clear()
            with self._ack_cv:
                self._ack_cv.notify_all()

    def _dispatch(self, stanza: str) -> bool:
        """Procesa una stanza. Devuelve True si hay que cerrar."""
        name = _local_name(stanza)
        if name == "message":
            message = XmppMessage(
                id=xml_attribute(stanza, "id"),
                sender=xml_attribute(stanza, "from"),
                to=xml_attribute(stanza, "to"),
                type=xml_attribute(stanza, "type"),
                body=_extract_body(stanza) or "",
                raw=stanza,
            )
            if self.on_message is not None:
                try:
                    self.on_message(message)
                except Exception:
                    # Un fallo del callback no debe tirar la conexion.
                    pass
            return False
        if name == "tdack":
            mi = xml_attribute(stanza, "mi")
            if mi:
                with self._ack_cv:
                    self._acks.add(mi)
                    self._ack_cv.notify_all()
            return False
        if name == "iq":
            if xml_attribute(stanza, "type") == "get":
                iq_id = xml_attribute(stanza, "id")
                sender = xml_attribute(stanza, "from")
                if iq_id:
                    to_attr = f" to='{xml_escape(sender)}'" if sender else ""
                    try:
                        self._send_raw(
                            f"<iq xmlns='{NS_CLIENT}' type='result' "
                            f"id='{xml_escape(iq_id)}'{to_attr}/>",
                            check=False,
                        )
                    except TodusError:
                        return True
            return False
        if name == "stream":
            return True
        return False
