# Pruebas realizadas

Fecha de actualización: **2026-11-16**. Entorno local: Linux, Python 3.14.4,
sin dependencias externas. Codespace de las pruebas: Python 3.14.2, yt-dlp
2026.10.26, Deno 2.9.8 y yt-dlp-ejs 0.8.0. Las pruebas con ToDus usan los dos
números de prueba del kkk (`58799457` emisor y `58548838` receptor).

> Estado actual, cuentas y Codespaces: [`ESTADO.md`](ESTADO.md).

## 1. Pruebas offline (sin red)

```bash
cd todus-lite
python3 -m unittest discover -s tests -v
```

Resultado: **55 pruebas OK** (`Ran 55 tests ... OK`).

| Archivo | Qué comprueba |
|---|---|
| `tests/test_protocol.py` | Tabla v1 (SHA, unicidad, sin `|`/XML), ida y vuelta de bytes, números/JID, tramas, límite 8192, CRC, desorden, duplicados, extensión. |
| `tests/test_todus_parse.py` | Stanzas abreviadas de ToDus (`<m>`, `<b>`, `t/i/f/o`), `<ok/>`, stream, body, atributos, escapes. |
| `tests/test_receiver.py` | El receptor reconstruye un fichero de 120 KB con tramas desordenadas y rechaza tramas corruptas. |
| `tests/test_download.py` | Detección de YouTube/páginas, calidades 360/480/720, reanudación HTTP (Range/.part), validación de MP4/WebM/AVI y SHA-256. |
| `tests/test_descargar.py` | `descargar` rechaza destino == emisor y números inválidos antes de tocar la red; con un `gh` simulado prueba el fallback multi-token, la creación/uso de Codespace, la copia de cookies, el borrado remoto y el apagado automático. |

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

### 3.3b YouTube real (Codespace → ToDus → teléfono)

- Enlace: `https://youtube.com/shorts/s1aE_t_iWhI`
- Descarga: **yt-dlp 2026.10.26** + **Deno 2.9.8** + **yt-dlp-ejs 0.8.0**
  + cookies de `.youtube.com` (25 cookies).
- Emisor: Codespace `todus-lite-4q6p9jqxv9rxfqpp9`, cuenta `5358799457`.
- Receptor: local, cuenta `5358548838`, salida a `/sdcard/Download`.
- Calidad: 480p (selector 360/480/720; sin límite de tamaño por defecto).
- Fichero descargado: 3.836.131 bytes (3,7 MiB).
- SHA-256: `3a0b1f6675506db90d200f0febd5477950678cb7c246ba612988264ad2c12c9c`
- Tramas: **766/766**, 0 rechazadas.
- Salida en el teléfono: `/sdcard/Download/d46a11db6c2b9c55.mp4`.
- SHA-256 recibido: **idéntico** al descargado.
- Resultado: **OK**. Es la prueba real completa: YouTube → Codespace →
  codificación → ToDus → teléfono → MP4 reproducible.

### 3.3c Comando `descargar` (real)

Prueba real de extremo a extremo con `descargar`:

- Enlace: `https://youtu.be/YahWlZoKHkY?si=bk6GKhAfBFl2gqbE`
- Calidad: **360p**; sin límite de tamaño.
- Salida: `/sdcard/Download/c95e4d4ed7115a6a.mp4`
- Tamaño: **21.334.362 bytes** (20,3 MiB).
- SHA-256: `d5de97897502efb32e1969e2835eef5a3849f48e70aa4780169abd3a5b68ef0f`
- Tramas: **4317/4317**, 0 rechazadas.
- Resultado: **OK**, SHA idéntico al descargado.

También se comprobó:

- `bash -n descargar` → sintaxis OK.
- Destino == emisor se rechaza antes de descargar; `--self` lo permite.
- `descargar` apaga el Codespace al terminar aunque ya estuviera encendido
  (salvo `--keep`/`TDS_KEEP_CODESPACE=1`).
- Tras un envío correcto borra `descargas/` del Codespace; `enviar.py
  --delete-after-send` hace lo mismo cuando se usa por separado.
- Sin sesión de GitHub: pide URL y número, detecta el fallo con
  `gh codespace list` y sale **sin** arrancar el receptor.
- Con un `gh` simulado: genera el script remoto, lo codifica en base64 y el
  script remoto conserva la URL con `?`/`&` y el número. Se verificó el
  contenido decodificado.
- La lógica del receptor (`receptor.py --once`) ya está probada en 3.2/3.3.

Realizado: ejecución real completa con token no interactivo y Codespace
nuevo (`todus-lite-vpwj76pxrx4phx6wp`), auto-arranque y auto-apagado.

### 3.3e Comando `descargar` 480p (2026-11-15/16)

- Enlace: `https://youtu.be/YahWlZoKHkY?si=d685bBMm2uRFlqrX`
- Calidad: **480p**; destino `58548838`; sin límite de tamaño.
- Cuenta: `michel3000006`; Codespace reutilizado
  `shocking-ghost-p79xx6vx5p95h6v49`.
- Descarga: el cliente web por defecto dio **HTTP 403**; `download.py`
  reintentó con **`web_embedded`** y descargó 22,3 MiB de vídeo + 5,8 MiB de
  audio.
- Fichero recibido: `/sdcard/Download/95c6350cf2b98fe7.mp4`
- Tamaño: **29.536.718 bytes**.
- SHA-256: `0474606cca2c75c2e880bfa19fe23e3b06828f29f1c5e61bacf2ffeee428fce2`
- Tramas: **5990/5990**, 0 rechazadas; SHA del emisor y del receptor idéntico.
- Codespace: apagado automáticamente al terminar.
- Log: `/tmp/descargar_yah_480_final_20261115_161850.log`.

### 3.3f Diagnóstico de YouTube 403

En el Codespace `shocking...` se probaron clientes con una sección de 2 s:

| Prueba | Resultado |
|---|---|
| Sin cookies | `Sign in to confirm you’re not a bot` |
| Cookies + `android` | Cliente omitido: no soporta cookies; solo imágenes |
| Cookies + `mweb` | Requiere PO Token; descarga HTTP 403 |
| Cookies + `tv` | `The page needs to be reloaded` |
| Cookies + `web_embedded` | **Descarga correcta** |

Conclusión: las cookies eran válidas, pero el cliente web necesitaba otro
enfoque. El fallback `web_embedded` quedó integrado y probado.

### 3.3d Comando `descargar` con watchdog (2026-11-12)

- Enlace: `https://youtube.com/shorts/pRNHiELPIhQ`
- Calidad: **360p**; destino `58548838`.
- Codespace: `todus-lite-vpwj76pxrx4phx6wp`, arrancado desde `Shutdown` y
  parado automáticamente hasta `Shutdown`.
- Fichero: `/sdcard/Download/95904373582f3b13.mp4`
- Tamaño: **5.172.226 bytes**.
- SHA-256: `67d1b41be895a7749a01b2c688e7f80e831b8d15e478712640a0aeb04c633aea`
- Tramas: **1033/1033**, 0 rechazadas.
- SHA del emisor y del receptor: **idéntico**.
- `TDS_STALL_SECONDS=180`: el envío real no se colgó. Con un `gh` simulado
  que no emite progreso, `descargar` abortó a los 3 s, limpió el FIFO y no
  dejó procesos.
- Multi-cuenta simulado: el token A sin Codespace y con 402 se descarta; el
  token B con `csB` disponible se usa, se copian las cookies y se configura
  el entorno. Test automatizado incluido en `tests/test_descargar.py`.
- Resultado: **OK**.

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

- Un envío real **posterior** al cambio de borrado/limpieza; el borrado y el
  apagado están cubiertos por tests y por la ejecución real anterior, pero no
  se repitió el envío completo después de ese último cambio.
- 720p por ToDus real. Sí se probó 480p (29,5 MiB), 360p (21,3 MiB), un Short
  de 5,2 MiB, un Short de 3,7 MiB y 64 KiB.
- TikTok/Instagram/Facebook/X/Vimeo reales; el código usa `yt-dlp`, pero no se
  validaron con enlaces reales.
- Reanudación del **envío** ToDus (la descarga sí se reanuda).
- Rotación/eliminación del secreto antiguo `TDS_COOKIES_B64`.
