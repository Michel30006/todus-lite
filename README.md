# ToDus Lite — enviar un vídeo como texto por ToDus

Versión **ligera** del proyecto `kkk` (Ing Inversa). No usa PostgreSQL, ni los
Servidores A/B, ni compilación C++. Todo es **Python puro** (solo biblioteca
estándar) y reutiliza el protocolo ya verificado del kkk:

1. Se descarga un vídeo desde un enlace directo HTTP(S).
2. Cada byte se convierte en un símbolo Unicode con la **tabla v1** del kkk.
3. El texto se fragmenta en tramas `TDS1` de como máximo 8192 bytes UTF-8.
4. Las tramas se envían por **ToDus (XMPP)** al número del receptor.
5. El receptor reensambla, decodifica y escribe el vídeo original.

El emisor se ejecuta en el **GitHub Codespace** (o cualquier Linux con Python
3.10+). El receptor se ejecuta en el **teléfono** (Termux) o en otro equipo.

## Estado actual (2026-11-16)

El proyecto está **funcional y probado de extremo a extremo**: YouTube →
Codespace → ToDus → teléfono. Última prueba real: vídeo `YahWlZoKHkY` en
**480p**, `29.536.718` bytes, `5990/5990` tramas, SHA-256 idéntico en
`/sdcard/Download/95c6350cf2b98fe7.mp4`.

- **55 pruebas offline OK**.
- Multi-cuenta con fallback por HTTP 402, reutilización de Codespaces y
  auto-arranque/auto-apagado.
- YouTube con `yt-dlp` + Deno/EJS + cookies; si el cliente por defecto da
  **403**, se reintenta con `web_embedded`.
- Tras un envío correcto, `descargar` borra el vídeo del Codespace y apaga el
  Codespace (salvo `--keep`).
- Estado detallado, cuentas, Codespaces, evidencia y pendientes:
  [`docs/ESTADO.md`](docs/ESTADO.md).

## Funcionalidades actuales

- **Protocolo v1 del kkk** reimplementado en Python puro: tabla de 256
  símbolos, tramas `TDS1`, CRC-32, reensamblado tolerante a desorden y
  duplicados.
- **Receptor** Python y lanzador con binario C++ opcional; normalización
  automática del `53`, escritura atómica y SHA-256.
- **Descarga** HTTP reanudable y `yt-dlp` para YouTube/TikTok/Instagram/
  Facebook/X/Vimeo, con calidades 360/480/720 y sin límite de tamaño por
  defecto.
- **Cookies Netscape** para YouTube, Deno + EJS y configuración persistente en
  el Codespace.
- **`descargar`** para Termux: URL + calidad + número, receptor local o
  `--remoto`, multi-token, selección/creación/reutilización de Codespace,
  sincronización de código, configuración remota, watchdog, comparación de
  SHA, borrado del vídeo y apagado automático.
- **`enviar.py`** interactivo o por argumentos, con `--file`, `--dry-run`,
  `--delete-after-send` y JWT por `TODUS_TOKEN`/`--token`.
- **Documentación** de uso, protocolo, pruebas, estado y continuidad.

## Inicio rápido

### 1. Receptor (en el teléfono, primero)

```bash
cd todus-lite
python3 receptor.py
```

Pide el número de teléfono de ese receptor. Puedes escribir:

- `58548838` → se convierte automáticamente en `5358548838`
- `5358548838` → se usa tal cual
- `+53 5854 8838` → se limpia y normaliza
- `5358548838@im.todus.cu` → JID completo

Espera a ver:

```text
Conectado como 5358548838@im.todus.cu/tds-lite-receiver
LISTO. Esperando tramas TDS1...
```

> **Importante:** el receptor debe estar escuchando **antes** de lanzar el
> emisor. Si se lanza después, las primeras tramas se pierden (ToDus no
> guarda el historial para este uso).

Si prefieres el binario C++ ya verificado del kkk, usa `./receptor.sh`; hace
la misma pregunta y antepone el 53, y elige el binario si lo encuentra.

### 2. Emisor (en el Codespace)

```bash
cd todus-lite
python3 enviar.py
```

El script pide:

```text
Enlace del video: https://ejemplo.com/video.mp4
Numero de telefono destino (sin 53 si es de 8 digitos) [58548838]:
```

Descarga el vídeo, lo codifica, se conecta a ToDus como la cuenta emisora
(por defecto `58799457` → `5358799457@im.todus.cu`) y envía las tramas.

Al terminar muestra el `job_id`, el número de tramas y el SHA-256. El receptor
muestra el fichero reconstruido en `/sdcard/Download` (o `recibidos/`) y su
SHA-256, que debe coincidir.

## Cambiar de receptor

En el teléfono, ejecuta `receptor.py` (o `receptor.sh`) y escribe el nuevo
número de 8 dígitos; el `53` se añade solo. En el emisor, escribe ese mismo
número cuando lo pida. No hay que tocar código.

También puedes fijar el número del receptor sin que lo pregunte:

```bash
TDS_NUMBER=55123456 ./receptor.sh
```

## Cuentas ToDus

| Papel | Número por defecto | JID |
|---|---|---|
| Emisor | `58799457` | `5358799457@im.todus.cu` |
| Receptor | `58548838` | `5358548838@im.todus.cu` |

Son los dos números de prueba que el proyecto kkk usó para verificar ToDus.
Cambia el emisor con la variable de entorno `TODUS_SENDER` o con `--from`:

```bash
TODUS_SENDER=55123456 python3 enviar.py
```

El JWT se pide en cada ejecución a `https://auth.todus.cu/v2/auth/token` con
el número (sin contraseña). **No se guardan tokens ni contraseñas.**

## Enlaces de vídeo

Se admiten:

- Enlaces **directos** `http://` o `https://` a un fichero (`.mp4`, `.webm`...).
- **YouTube, TikTok, Instagram, Facebook, X/Twitter, Vimeo...** mediante
  `yt-dlp`. Para YouTube hace falta un runtime JavaScript (**Deno**) y el
  solver **EJS**; el `.devcontainer` del proyecto los instala solos.

El emisor detecta si el enlace es una página y usa `yt-dlp`; si es un fichero
directo, usa la descarga HTTP normal. En YouTube/TikTok/etc. la calidad se
elige al descargar (**360p**, **480p** o **720p**) y **no hay límite de tamaño
por defecto**; un 720p puede pesar mucho y tardar bastante en enviarse.

### Cookies de YouTube

YouTube suele exigir cookies de una sesión iniciada, sobre todo desde IPs de
Codespace. El emisor busca automáticamente:

```text
~/.config/tds/cookies.txt
```

o la ruta de `--cookies` / `TDS_COOKIES_FILE`. `descargar` copia las cookies
locales (`~/.config/todus-lite/cookies.txt`, o `/sdcard/Download/juj.txt`) a
`~/.config/tds/cookies.txt` en el Codespace antes de descargar. El secreto
antiguo `TDS_COOKIES_B64` ya no es necesario para el flujo actual. **No se
guardan en el repositorio.**

Formato: fichero de cookies **Netscape** exportado del navegador
(por ejemplo, la extensión "Get cookies.txt LOCALLY"). Contiene cookies de
`.youtube.com` (`SID`, `HSID`, `SSID`, `APISID`, `SAPISID`, `LOGIN_INFO`,
`__Secure-*`).

## Comando rápido en Termux: `descargar`

El repo incluye el ejecutable `descargar`. Instálalo una vez en el `PATH`:

```bash
ln -sf /root/todus-lite/descargar /usr/local/bin/descargar
```

La primera vez hay que autenticar GitHub (solo una vez):

```bash
gh auth login -h github.com
gh auth refresh -h github.com -s codespace
```

Después basta con:

```bash
descargar
```

Pide **URL**, **calidad** (360/480/720) y **número destino**, arranca el
receptor local, conecta al Codespace (lo arranca si está parado y sincroniza
`enviar.py` y `tds_lite/*.py`), descarga el vídeo con las cookies y lo envía.
El fichero aparece en `/sdcard/Download`.

- Por defecto asume que el teléfono que ejecuta `descargar` es el receptor y
  arranca `receptor.py` con el número indicado.
- Si envías a **otro teléfono**, ejecuta `descargar --remoto`; ese teléfono
  debe tener el receptor ya escuchando.
- El destino debe ser distinto del emisor (`TODUS_SENDER`); si coincide,
  `descargar` se niega antes de descargar. `--self` lo permite solo para
  pruebas.
- Al terminar, borra el vídeo descargado del Codespace y lo **para** (aunque
  ya estuviera encendido). Usa `--keep` (o `TDS_KEEP_CODESPACE=1`) para
  dejarlo encendido; el vídeo se borra igualmente tras un envío correcto.
- Variables: `TDS_CODESPACE`, `TODUS_SENDER`, `TDS_MAX_MIB` (opcional;
  vacío o `0` = sin límite), `TDS_OUT_DIR`, `TDS_KEEP_CODESPACE`,
  `TDS_ALLOW_SELF`, `TDS_STALL_SECONDS` (por defecto 300; cancela si el
  envío deja de avanzar; `0` lo desactiva), `TDS_GH_TOKEN_DIR`,
  `TDS_GH_TOKEN_FILE`, `TDS_COOKIES_FILE`, `TDS_REMOTE_DIR` (def.
  `/tmp/todus-lite`), `TDS_YTDLP_PLAYER_CLIENT` (fuerza el cliente de YouTube,
  por ejemplo `web_embedded`).
- Tokens multi-cuenta: guarda cada PAT en
  `~/.config/todus-lite/tokens/<cuenta>.token` (permisos `600`). `descargar`
  prueba primero `GH_TOKEN`, luego esos ficheros y al final
  `~/.config/todus-lite/gh_token`. Si una cuenta no tiene cuota/facturación
  (HTTP 402), pasa a la siguiente. Si no hay Codespace del repo, reutiliza
  cualquier Codespace de la cuenta; solo crea uno si la cuenta tiene acceso al
  repo.
- Cookies: usa `~/.config/todus-lite/cookies.txt` (o `/sdcard/Download/juj.txt`)
  y las copia al Codespace; `.devcontainer/setup.sh` instala/verifica
  yt-dlp, Deno, ffmpeg y la configuración de yt-dlp.
- Si `gh` no tiene sesión, el script lo dice y no envía nada.
- Opcional: guarda un PAT en `~/.config/todus-lite/gh_token` (permisos `600`)
  para autenticación no interactiva.

## Límites y tiempos

- Sin límite de tamaño por defecto. Límite opcional con `--max-mib` o
  `MAX_VIDEO_BYTES` (`0` = sin límite).
- Trama máxima: **8192 bytes UTF-8**.
- Pausa entre tramas: **120 ms** (`SEND_DELAY_MS`).
- La tabla v1 ocupa ~**1,66 bytes de texto por byte de vídeo**.
- Referencia: 64 KiB → 14 tramas; 1 MiB → 214 tramas; 25 MiB → ~5370 tramas
  (~11 minutos solo de envío, más los acuses).
- Prueba real de YouTube: Short de 3,7 MiB → **766 tramas** y **SHA-256
  idéntico** en el teléfono.

## Estructura

```text
todus-lite/
├── enviar.py              # emisor interactivo (Codespace)
├── descargar              # comando rápido Termux: URL + número -> envía
├── receptor.py            # receptor interactivo (teléfono / Linux)
├── receptor.sh            # lanzador que pregunta número y usa C++ o Python
├── .devcontainer/         # Codespace: sshd, Deno/EJS, yt-dlp y cookies
├── tds_lite/
│   ├── table_v1.py        # tabla de codificación v1 (256 símbolos)
│   ├── protocol.py        # codificación, tramas TDS1, reensamblado, JID
│   ├── todus.py           # JWT + cliente XMPP ToDus (stdlib)
│   └── download.py        # HTTP(S) + yt-dlp (YouTube...), calidad y SHA-256
├── tests/
│   ├── test_protocol.py
│   ├── test_todus_parse.py
│   ├── test_receiver.py
│   ├── test_download.py      # URLs, calidades, reanudación y vídeo
│   ├── test_descargar.py     # guardas, multi-token y apagado
│   └── interop_kkk.py        # tramas Python -> receptor C++ del kkk
└── docs/
    ├── ESTADO.md             # estado actual, cuentas y evidencia
    ├── USO.md
    ├── PROTOCOLO.md
    ├── PRUEBAS.md
    └── CONTINUIDAD.md        # decisiones, historial y cómo continuar
```

## Pruebas

```bash
python3 -m unittest discover -s tests -v       # 55 pruebas offline
python3 tests/interop_kkk.py                   # contra el receptor C++ del kkk
python3 enviar.py --file mi_video.mp4 --to 58548838 --dry-run
```

La prueba de interoperabilidad necesita el binario `tds_receiver` del kkk. Si
no existe, se omite y no falla.

## Variables de entorno

| Variable | Uso | Defecto |
|---|---|---|
| `TODUS_SENDER` | número emisor | `58799457` |
| `TODUS_TOKEN` | JWT ya obtenido (evita pedirlo) | vacío |
| `TODUS_AUTH_URL` | endpoint del JWT | `https://auth.todus.cu/v2/auth/token` |
| `TDS_COOKIES_FILE` | cookies de YouTube | `~/.config/tds/cookies.txt` |
| `TDS_YTDLP_PLAYER_CLIENT` | fuerza cliente YouTube (`web_embedded`, etc.) | automático |
| `MAX_VIDEO_BYTES` | límite opcional de descarga | sin límite |
| `SEND_DELAY_MS` | pausa entre tramas | `120` |
| `TDS_NUMBER` | número del receptor (receptor.sh) | pregunta / `58548838` |
| `TDS_OUT_DIR` | salida del receptor | `/sdcard/Download` o `recibidos/` |
| `TDS_RECEIVER_BIN` | binario C++ del kkk | `../kkk/build/client/tds_receiver` |
| `TDS_CODESPACE` | Codespace concreto | detectar/reutilizar/crear |
| `TDS_REPO` | repo del Codespace | `Michel30006/todus-lite` |
| `TDS_REMOTE_DIR` | carpeta remota de trabajo | `/tmp/todus-lite` |
| `TDS_GH_TOKEN_DIR` | carpeta de tokens multi-cuenta | `~/.config/todus-lite/tokens` |
| `TDS_GH_TOKEN_FILE` | token único (compatibilidad) | vacío |
| `TDS_KEEP_CODESPACE` | no apagar el Codespace | `0` |
| `TDS_ALLOW_SELF` | permitir destino == emisor | `0` |
| `TDS_STALL_SECONDS` | cancelar si no hay avance | `300` |

## Cómo funciona (resumen)

- **Codificación:** `byte 0xNN → TABLE[0xNN]`. La tabla no contiene `|` ni
  caracteres especiales XML, así que no hacen falta escapes.
- **Trama:** `TDS1|job_id|transfer_id|indice|total|version|crc32|payload`.
- **CRC-32** (zlib) del payload en UTF-8; el receptor rechaza tramas corruptas.
- **Auth:** protobuf `{field 1: "53"+número, field 3: "2.1.2"}` al endpoint de
  ToDus; el campo 2 de la respuesta es el JWT.
- **XMPP:** TLS directo a `im.todus.cu:5222`, SASL PLAIN con el JWT, bind de
  recurso, presencia con prioridad 10, mensajes `type='chat'` y acuse
  `<tdack mi='...'/>`.

Detalle completo en [docs/PROTOCOLO.md](docs/PROTOCOLO.md).

## Compatibilidad con el receptor del kkk

Las tramas son idénticas a las del kkk. El binario C++ `tds_receiver`
(reconstrucción verificada) puede recibir lo que envía `enviar.py`. Esto se
probó generando 214 tramas de 1 MiB con este proyecto y reconstruyéndolas con
el binario C++: SHA-256 idéntico byte a byte. Ver
[docs/PRUEBAS.md](docs/PRUEBAS.md).

## Seguridad y privacidad

- No se incluyen tokens ni contraseñas en el repositorio. El JWT se obtiene en
  cada ejecución o se pasa por `TODUS_TOKEN`.
- Las cookies de YouTube son equivalentes a la sesión de tu cuenta de Google:
  trátalas como una contraseña. En local están en
  `~/.config/todus-lite/cookies.txt` (600) y en el Codespace en
  `~/.config/tds/cookies.txt` (600). No se publican en el repo.
- El vídeo viaja por TLS hasta el servidor de ToDus; no hay cifrado extremo a
  extremo propio (igual que en kkk).
- El receptor acepta cualquier trama TDS1 dirigida a su cuenta; no hay firma
  ni autenticación por remitente. No uses esto para datos sensibles.
- Los números por defecto son los de prueba del kkk. Cámbialos si no son los
  tuyos.

## Limitaciones conocidas

- ToDus es un protocolo no documentado oficialmente; puede cambiar sin aviso.
- El receptor debe conectarse antes que el emisor.
- Si se corta la **descarga**, se reanuda al volver a ejecutar (HTTP Range /
  yt-dlp `.part`). Si se corta el **envío** por ToDus, hay que reiniciarlo
  desde el principio; el receptor tolera duplicados.
- El DNS de ToDus puede fallar de forma intermitente; hay reintentos y caché
  de IP, pero puede tardar unos segundos.
- YouTube cambia a menudo: si falla, actualiza `yt-dlp` y renueva las cookies.
  Sin Deno/EJS, YouTube solo devuelve imágenes (storyboards). Si el cliente
  por defecto devuelve HTTP 403, el flujo reintenta con `web_embedded`; se
  puede forzar con `TDS_YTDLP_PLAYER_CLIENT`.
- La cuenta `Michel30006` puede recibir HTTP 402 por facturación/cuota al
  arrancar su Codespace. `descargar` prueba otra cuenta o reutiliza un
  Codespace existente. Las cuentas sin acceso al repo privado no pueden crear
  uno nuevo.
- El DNS/red de ToDus puede fallar de forma intermitente también desde el
  Codespace; el emisor reintenta y acepta un JWT por `--token`.
- Un vídeo grande tarda mucho: sin límite, un 720p puede superar 100 MiB y
  tardar horas. El límite práctico es el ritmo de ToDus.
- Las descargas son **reanudables**: si se corta la conexión, vuelve a
  ejecutar el mismo comando y continúa desde el último byte. HTTP usa
  `Range` + `.part`; yt-dlp conserva su directorio `.tds-ytdlp-*`.

## Documentación

| Documento | Contenido |
|---|---|
| [docs/ESTADO.md](docs/ESTADO.md) | Estado actual, funcionalidades, cuentas, Codespaces, evidencia y pendientes. |
| [docs/USO.md](docs/USO.md) | Guía paso a paso para Codespace y teléfono. |
| [docs/PROTOCOLO.md](docs/PROTOCOLO.md) | Tabla, trama, auth, XMPP y compatibilidad. |
| [docs/PRUEBAS.md](docs/PRUEBAS.md) | Pruebas offline, interop C++, ToDus real y YouTube. |
| [docs/CONTINUIDAD.md](docs/CONTINUIDAD.md) | Decisiones, historial y cómo retomar el proyecto. |

## Licencia

No definida todavía. El material de investigación y los números de prueba
proceden del proyecto kkk; revísalos antes de publicar el repositorio.
