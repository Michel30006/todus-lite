# Pruebas realizadas

Fecha: **2026-11-08**. Entorno: Linux, Python 3.14.4, sin dependencias
externas. Las pruebas con ToDus usan los dos números de prueba del kkk
(`58799457` emisor y `58548838` receptor).

## 1. Pruebas offline (sin red)

```bash
cd todus-lite
python3 -m unittest discover -s tests -v
```

Resultado: **35 pruebas OK** (`Ran 35 tests ... OK`).

| Archivo | Qué comprueba |
|---|---|
| `tests/test_protocol.py` | Tabla v1 (SHA, unicidad, sin `|`/XML), ida y vuelta de bytes, números/JID, tramas, límite 8192, CRC, desorden, duplicados, extensión. |
| `tests/test_todus_parse.py` | Stanzas abreviadas de ToDus (`<m>`, `<b>`, `t/i/f/o`), `<ok/>`, stream, body, atributos, escapes. |
| `tests/test_receiver.py` | El receptor reconstruye un fichero de 120 KB con tramas desordenadas y rechaza tramas corruptas. |

## 2. Interoperabilidad con el receptor C++ del kkk

Objetivo: demostrar que las tramas generadas por este proyecto son idénticas
a las que espera el receptor verificado del kkk.

```bash
python3 tests/interop_kkk.py
```

- Fichero: 1 MiB aleatorio (`/dev/urandom`).
- Tramas generadas: **214**.
- Receptor: `kkk/build/client/tds_receiver --frames ...`.
- El fichero es aleatorio en cada ejecución. Ejemplos de SHA-256 original =
  reconstruido:
  - `27fbab15fd2099e014e6b77ca11a56b9e37442f4231c51d46ceed635be19f3dd`
  - `acdd86c760e689c00b2ca64a9c83acbcba1fc2a48027f84933ffbc2cd1e130a0`
    (última ejecución al escribir este documento)
- Resultado: **OK**, byte a byte idéntico en todas las ejecuciones.

## 3. ToDus real

Estas pruebas conectan de verdad a `im.todus.cu`. No descargan vídeos de
Internet: el fichero de entrada se genera localmente con `/dev/urandom`.

### 3.1 JWT

```python
from tds_lite.todus import fetch_token
fetch_token("5358799457")
```

Resultado: JWT de **165 caracteres** (`eyJhbGciOiJI...`). OK.

### 3.2 Conexión XMPP y bind

```python
from tds_lite.todus import XmppClient
c = XmppClient(username="5358799457", resource="tds-lite-test")
c.connect()
print(c.jid)   # 5358799457@im.todus.cu/tds-lite-test
c.close()
```

Resultado: **OK**, cierre limpio. (En una ejecución hubo un fallo transitorio
de DNS; por eso el código ahora reintenta y cachea la IP.)

### 3.3 Una trama (25 bytes)

- Emisor: `5358799457` (`tds-lite-debug`).
- Receptor: `5358548838` (`tds-lite-receiver`), en el Codespace, con `--once`.
- Datos: `b"hello world from tds-lite"`.
- `job_id`: `036c30e9c597737f`.
- Tramas: 1/1.
- SHA-256 recibido:
  `b0a96be9eb206925ef79c1ed005a8f8c567c25b528b1ee68fc0aa1df8691fd91`.
- Resultado: **OK**, acuse `<tdack>` y fichero reconstruido.

### 3.4 Fichero de 64 KiB (14 tramas)

- Emisor: `5358799457` (`tds-lite-sender`).
- Receptor: `5358548838` (`tds-lite-receiver`), en el Codespace, con `--once`.
- Entrada: 65536 bytes aleatorios.
- SHA-256 de entrada:
  `bcadffcd9fb12b5d622881393eba3b4e244a77724bffc36fcda7917f964f8d7f`.
- `job_id`: `48cf8057b2ff8aba`.
- Tramas: **14/14**, 0 rechazadas.
- SHA-256 reconstruido: **idéntico**.
- Salida del receptor:

```text
ARCHIVO RECIBIDO Y RECONSTRUIDO
  job:     48cf8057b2ff8aba
  tamano:  65536 bytes
  sha256:  bcadffcd9fb12b5d622881393eba3b4e244a77724bffc36fcda7917f964f8d7f
  tramas:  14/14
```

Resultado: **OK**. Es un recorrido completo real:
descarga/codificación/framing → ToDus → reensamblado → fichero.

> Nota: en el primer intento de 64 KiB se perdieron los acuses por un fallo
> transitorio de DNS y el emisor agotó sus reintentos. Se añadieron reintentos
> de DNS, caché de IP y una política de reconexión menos agresiva. El segundo
> intento completó las 14 tramas.

## 4. Cómo reproducir las pruebas sin el teléfono

En el Codespace se pueden lanzar emisor y receptor a la vez (dos cuentas):

```bash
# Terminal 1: receptor en primer plano
python3 -u receptor.py --number 58548838 --out /tmp/recv --once

# Terminal 2: generar un fichero y enviarlo
head -c 65536 /dev/urandom > /tmp/entrada.bin
sha256sum /tmp/entrada.bin
python3 -u enviar.py --file /tmp/entrada.bin --to 58548838 --from 58799457
```

Compara el SHA-256 del emisor y del receptor.

## 5. Qué no se ha probado

- El receptor ejecutándose en el teléfono real del usuario (solo en el
  Codespace).
- Vídeos grandes (5/25 MiB) por ToDus real; solo se midió 64 KiB.
- Enlaces de vídeo reales (no se descargó ningún vídeo de Internet en estas
  pruebas).
- Extracción desde YouTube/TikTok (no implementada).
