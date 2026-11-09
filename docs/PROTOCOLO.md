# Protocolo

Este documento describe el protocolo que usa `todus-lite`. Es el mismo del
proyecto kkk (`shared/src/encoding.cpp`, `framing.cpp`, `reassembler.cpp`,
`xmpp.cpp` y `protobuf_auth.cpp`), reimplementado en Python puro.

## 1. Codificación byte → texto (tabla v1)

La tabla vive en [`tds_lite/table_v1.py`](../tds_lite/table_v1.py) y es una
copia exacta de `kkk/shared/resources/table_v1.txt`:

- 256 símbolos únicos, uno por cada valor de byte `0x00..0xFF`.
- 88 símbolos ocupan 1 byte UTF-8 y 168 ocupan 2 bytes (media 1.6562).
- SHA-256 de los 256 símbolos concatenados en UTF-8:
  `c6cfa82beb0eabc11bcd1158264d3ec3de152469236f1280703c62cbfb84a26c`.
- No contiene `|` (separador de trama) ni `< > & " '` (especiales de XML),
  así que el payload no necesita escapes.

Codificar:

```python
texto = data.decode("latin-1").translate(ENC_TABLE)   # str
payload_utf8 = texto.encode("utf-8")                   # bytes que viajan
```

Decodificar:

```python
bytes_originales = texto.translate(DEC_TABLE).encode("latin-1")
```

Antes de decodificar se valida que todos los caracteres pertenecen a la tabla;
si aparece un símbolo ajeno (por ejemplo `|`), la trama se rechaza. Esto evita
que un carácter no mapeado se cuele como byte por `latin-1`.

## 2. Trama TDS1

```text
TDS1|<job_id>|<transfer_id>|<chunk_index>|<total_chunks>|<enc_ver>|<crc32>|<payload>
```

| Campo | Regla |
|---|---|
| `TDS1` | Magic fijo. |
| `job_id` | `[A-Za-z0-9_-]{1,64}`. En este proyecto: 16 hex (`secrets.token_hex(8)`). |
| `transfer_id` | Igual que `job_id`. |
| `chunk_index` | `0..total_chunks-1`. |
| `total_chunks` | `1..1_000_000`. |
| `enc_ver` | `1` (tabla v1). |
| `crc32` | CRC-32 IEEE (zlib) del payload UTF-8, 8 hex minúsculas. |
| `payload` | Texto de la tabla v1; no contiene `|`. |

El receptor comprueba CRC **antes** de decodificar y valida que el payload
solo usa símbolos de la tabla.

### Presupuesto de payload

Para que ninguna trama supere `MAX_STANZA_BYTES` (8192), se reserva una
cabecera conservadora contando 5 dígitos para índice, total y versión:

```text
header = 4 + 1 + len(job_id) + 1 + len(transfer_id) + 1
       + 5 + 1 + 5 + 1 + 5 + 1 + 8 + 1
budget = MAX_STANZA_BYTES - header
```

Con ids de 16 caracteres: `header = 66`, `budget = 8126` bytes UTF-8.

El texto codificado se divide en trozos de hasta `budget` bytes **sin romper un
símbolo UTF-8**: si el corte cae en un byte de continuación (`0b10xxxxxx`), se
retrocede un byte (los símbolos v1 miden 1 o 2 bytes). Cada trozo se decodifica
de nuevo a `str` para construir el payload de la trama.

El tamaño real de la trama se comprueba al serializar; si excede
`MAX_STANZA_BYTES`, se aborta.

### CRC y reensamblado

- `crc32 = zlib.crc32(payload.encode("utf-8")) & 0xFFFFFFFF`.
- El receptor agrupa por `(job_id, transfer_id)`.
- Tolera tramas desordenadas y duplicadas.
- Cuando tiene todos los índices `0..total-1`, decodifica cada payload y
  concatena en orden.
- No hay metadatos de tamaño/SHA en el protocolo (eso era cosa del Servidor A
  del kkk). La integridad se garantiza con CRC por trama y con la comparación
  del SHA-256 que muestran emisor y receptor.

## 3. Números y JID

`normalize_number()` en [`tds_lite/protocol.py`](../tds_lite/protocol.py):

| Entrada | Salida |
|---|---|
| `58548838` (8 dígitos) | `5358548838@im.todus.cu` |
| `5358548838` | `5358548838@im.todus.cu` |
| `+53 5854 8838` | `5358548838@im.todus.cu` |
| `5358548838@im.todus.cu` | sin cambios |

Regla: se quitan espacios, guiones y `+`; si son 8 dígitos se antepone `53`;
si son 10 y empiezan por `53`, se aceptan; si hay `@`, se respeta el JID.

## 4. Autenticación ToDus (JWT)

`POST https://auth.todus.cu/v2/auth/token` con `Content-Type:
application/x-protobuf` y cuerpo protobuf:

```text
field 1 (string) = "53" + telefono     (usuario)
field 2 (string) = password            (opcional; este proyecto no lo usa)
field 3 (string) = "2.1.2"             (versión del cliente)
```

La respuesta protobuf trae el JWT en el **field 2**. Se acepta cualquier campo
desconocido con wire type 0/1/2/5.

Implementación: `fetch_token()` en
[`tds_lite/todus.py`](../tds_lite/todus.py). Reintenta ante errores de red/DNS
(no ante un HTTP de autenticación).

## 5. XMPP / ToDus

Secuencia exacta (port de `XmppClient::connect` del kkk):

1. **TLS directo** a `im.todus.cu:5222` (no STARTTLS). Se verifica el
   certificado y el hostname (por defecto).
2. Enviar:

   ```xml
   <?xml version='1.0'?><stream:stream to='im.todus.cu'
     xmlns='jabber:client'
     xmlns:stream='http://etherx.jabber.org/streams' version='1.0'>
   ```

3. Esperar `<stream:features>`.
4. **SASL PLAIN**:

   ```xml
   <auth xmlns='urn:ietf:params:xml:ns:xmpp-sasl' mechanism='PLAIN'>
     base64("\0" + usuario + "\0" + JWT)
   </auth>
   ```

   ToDus puede responder `<success/>` o su forma abreviada `<ok/>`.
5. Reabrir el stream (sin declaración XML) y esperar features.
6. **Bind** clásico:

   ```xml
   <iq xmlns='jabber:client' type='set' id='bind_1'>
     <bind xmlns='urn:ietf:params:xml:ns:xmpp-bind'>
       <resource>tds-lite-receiver</resource>
     </bind>
   </iq>
   ```

   La respuesta contiene `<jid>...</jid>`.
7. Enviar `<session xmlns='urn:ietf:params:xml:ns:xmpp-session'/>` (se ignora).
8. Enviar presencia con prioridad alta:

   ```xml
   <presence><priority>10</priority></presence>
   ```

   Esto hace que ToDus entregue los mensajes a este recurso y no a la app
   Android.

9. Cada trama se envía como:

   ```xml
   <message xmlns='jabber:client' type='chat' to='5358548838@im.todus.cu'
            id='tds-1-...'><body>TDS1|...</body></message>
   ```

10. El servidor acusa con `<tdack mi='tds-1-...'/>`. El emisor espera ese
    acuse (`ACK_TIMEOUT` 15 s) y reintenta si falta.

### Stanzas abreviadas

ToDus puede abreviar elementos y atributos. El parser normaliza:

| Recibido | Equivale a |
|---|---|
| `<m>` | `message` |
| `<b>` | `body` |
| `<p>` | `presence` |
| `<ok/>` | `success` |
| `t`, `i`, `f`, `o` | `type`, `id`, `from`, `to` |

El parser extrae stanzas completas del stream respetando anidamiento,
comentarios, CDATA y etiquetas auto-cerradas. Está probado con las formas
abreviadas en `tests/test_todus_parse.py`.

## 6. Límites y ritmo

| Límite | Valor | Origen |
|---|---|---|
| Stanza máxima | 8192 bytes UTF-8 | investigación del kkk |
| Pausa entre tramas | 120 ms (configurable) | valor conservador del kkk |
| Acuse | `<tdack mi='...'/>` | protocolo reconstruido |
| JWT | caduca ~24 h | se pide nuevo en cada ejecución |
| Recurso | `tds-lite-sender` / `tds-lite-receiver` | configurable |

## 7. Compatibilidad

El formato de trama es idéntico al del kkk. Prueba realizada:

- 1 MiB aleatorio → 214 tramas generadas por `tds_lite.protocol.build_frames`.
- El binario C++ `kkk/build/client/tds_receiver --frames ...` las reensambló.
- SHA-256 y comparación byte a byte idénticos.

Resultado en [PRUEBAS.md](PRUEBAS.md).
