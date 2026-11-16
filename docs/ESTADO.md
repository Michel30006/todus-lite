# Estado actual del proyecto

**Fecha:** 2026-11-16

**Repositorio:** `https://github.com/Michel30006/todus-lite` (privado)

**Rama:** `main`

**Commit de código de esta actualización:** `e443e98`

## 1. Resumen

`todus-lite` es una reimplementación ligera de `kkk` en Python puro (solo
biblioteca estándar) para **descargar un vídeo, codificarlo como texto con la
tabla v1, enviarlo por ToDus (XMPP) y reconstruirlo en el teléfono**.

El flujo principal ya funciona de extremo a extremo:

```text
YouTube / URL directa
        ↓
Codespace (descarga + yt-dlp + cookies + codificación)
        ↓  tramas TDS1 por ToDus/XMPP
Teléfono (receptor.py / receptor.sh)
        ↓
/sdcard/Download/<job_id>.mp4
```

La última prueba real completada fue un vídeo de YouTube en **480p**:

| Dato | Valor |
|---|---|
| URL | `https://youtu.be/YahWlZoKHkY` |
| Calidad | 480p |
| Destino | `58548838` |
| Fichero recibido | `/sdcard/Download/95c6350cf2b98fe7.mp4` |
| Tamaño | `29.536.718` bytes |
| SHA-256 | `0474606cca2c75c2e880bfa19fe23e3b06828f29f1c5e61bacf2ffeee428fce2` |
| Tramas | `5990/5990` |
| Rechazadas | `0` |
| Resultado | SHA idéntico en emisor y receptor |

## 2. Funcionalidades actuales

### Protocolo y receptor

- Tabla v1 exacta del kkk: 256 símbolos, sin `|` ni caracteres especiales XML.
- Tramas `TDS1` de máximo 8192 bytes UTF-8, con CRC-32.
- Reensamblado tolerante a duplicados y desorden.
- Normalización de números: 8 dígitos → `53` + 8; JID completo respetado.
- `receptor.py`: escritura atómica, `--number`, `--out`, `--once`, `--verbose`.
- `receptor.sh`: elige el binario C++ del kkk si existe; si no, Python.
- Interoperabilidad verificada con el receptor C++ del kkk (214 tramas, 1 MiB).

### Descarga

- Enlaces directos HTTP(S), con `Range` y `.part` para reanudar.
- YouTube, TikTok, Instagram, Facebook, X/Twitter, Vimeo, etc. con `yt-dlp`.
- Calidades **360p, 480p y 720p**; por defecto **sin límite de tamaño**.
- Límite opcional con `--max-mib` o `MAX_VIDEO_BYTES`.
- Cookies Netscape para YouTube, Deno + EJS para el reto JavaScript.
- Rechazo de HTML y validación de que el resultado sea un vídeo real.
- SHA-256 calculado al terminar.
- Si YouTube devuelve **HTTP 403**, “solo imágenes” o “formato no disponible”,
  `download.py` reintenta automáticamente con el cliente **`web_embedded`**.
  Se puede forzar otro cliente con `TDS_YTDLP_PLAYER_CLIENT` (por ejemplo,
  `web_embedded`).

### Emisor `enviar.py`

- Interactivo o por argumentos: `--url`, `--file`, `--to`, `--from`,
  `--quality`, `--max-mib`, `--cookies`, `--cookies-from-browser`,
  `--token`, `--dry-run`, `--send-delay-ms`, `--ack-timeout`, `--retries`,
  `--frame-bytes`, `--resource`, `--insecure-tls`.
- Autenticación ToDus con JWT obtenido en cada ejecución o pasado por
  `TODUS_TOKEN`/`--token`.
- Reintentos de DNS, conexión y tramas; reconexión si se cae XMPP.
- `--delete-after-send`: borra el vídeo descargado del Codespace tras un
  envío correcto.

### Comando `descargar` (Termux)

- Pide **URL**, **calidad** y **número destino**.
- Arranca el receptor local salvo `--remoto`.
- Rechaza destino == emisor antes de descargar (`--self` lo permite).
- **Multi-cuenta:** prueba `GH_TOKEN`, luego
  `~/.config/todus-lite/tokens/*.token|*.txt` y al final
  `~/.config/todus-lite/gh_token`.
- Si una cuenta no tiene cuota/facturación (**HTTP 402**), pasa a la siguiente.
- Busca un Codespace del repo; si no existe, reutiliza **cualquier Codespace**
  de la cuenta; si no hay ninguno y la cuenta tiene acceso al repo, crea uno.
- Arranca el Codespace si está apagado, sincroniza `enviar.py` y
  `tds_lite/*.py`, copia las cookies y ejecuta `.devcontainer/setup.sh`.
- Instala/verifica `yt-dlp`, Deno/EJS y `ffmpeg`.
- Watchdog `TDS_STALL_SECONDS` (def. 300; `0` desactiva) para no quedar colgado.
- Compara SHA-256 del emisor y del receptor.
- Tras un envío correcto, **borra `descargas/` del Codespace**.
- **Apaga siempre el Codespace al terminar**, aunque ya estuviera encendido,
  salvo `--keep` o `TDS_KEEP_CODESPACE=1`.
- Si el envío falla, conserva la descarga para poder reintentar; el Codespace
  se apaga igualmente.

### Codespace / `.devcontainer`

- `sshd`, Python, Deno, EJS, `yt-dlp` y `ffmpeg`.
- Cookies persistentes en `~/.config/tds/cookies.txt` con permisos `600`.
- Configuración de `yt-dlp` en `~/.config/yt-dlp/config`.
- El secreto `TDS_COOKIES_B64` existió en el Codespace antiguo; el flujo
  actual copia las cookies locales al Codespace en cada ejecución.

## 3. Pruebas

```bash
cd /root/todus-lite
python3 -m unittest discover -s tests -v
```

Resultado actual: **55 pruebas OK** (`Ran 55 tests ... OK`).

Incluyen:

- Tabla v1, protocolo, CRC, desorden, duplicados y extensión.
- Parser de stanzas ToDus.
- Reconstrucción del receptor.
- Descarga HTTP, reanudación, validación de medios, calidades y SHA.
- Guardas de `descargar`, fallback multi-token, copia de cookies y apagado
  automático del Codespace.

Evidencia real adicional:

- YouTube Short 360p: 5.172.226 bytes, 1033/1033, SHA idéntico.
- YouTube `YahWlZoKHkY` 360p: 21.334.362 bytes, 4317/4317, SHA idéntico.
- YouTube `YahWlZoKHkY` **480p**: 29.536.718 bytes, 5990/5990, SHA idéntico.
- Interop C++: 214 tramas, 1 MiB, SHA idéntico.
- ToDus real: 1 trama y 64 KiB, SHA idéntico.

## 4. Estado de cuentas y Codespaces

Comprobado el 2026-11-16: **todos los Codespaces están en `Shutdown`**.

### Cuenta `Michel30006`

- Token en `~/.config/todus-lite/gh_token` (600). **Conservar** por indicación
  del usuario.
- Codespace del proyecto: `todus-lite-vpwj76pxrx4phx6wp`.
- Arrancarlo devuelve **HTTP 402** (`billing issue` / `currently disallowed`):
  no es un fallo del token ni del script.
- El Codespace antiguo `todus-lite-4q6p9jqxv9rxfqpp9` ya no existe.

### Cuenta `michel3000006`

- Token en `~/.config/todus-lite/tokens/cuenta2.token` (600).
- **No tiene acceso** al repo privado `Michel30006/todus-lite`.
- Codespaces:
  - `shocking-ghost-p79xx6vx5p95h6v49` (repo `michel3000006/1`): usado para la
    prueba real de 480p; arranca, sincroniza y configura correctamente.
  - `miniature-system-jr9xxg6xprj72qvwv` (repo `michel3000006/2`): disponible,
    pero en una prueba anterior el SSH dio `context deadline exceeded`.
- `descargar` puede reutilizar cualquiera de ellos porque el fallback a
  cualquier Codespace existente está implementado.

### Cookies

- `~/.config/todus-lite/cookies.txt` (600): 25 cookies `.youtube.com`,
  4137 bytes, filtradas desde `/sdcard/Download/juj.txt`.
- `/sdcard/Download/juj.txt`: export completo (sensible; fuera del repo).
- El secreto antiguo `TDS_COOKIES_B64` (~7972 bytes) no es recuperable porque
  el Codespace antiguo fue eliminado; no es necesario para el flujo actual.

## 5. YouTube: 403 y cliente `web_embedded`

Diagnóstico realizado en el Codespace `shocking...`:

| Prueba | Resultado |
|---|---|
| Sin cookies | `Sign in to confirm you’re not a bot` |
| Cookies + cliente `android` | Cliente omitido: no soporta cookies; solo imágenes |
| Cookies + `mweb` | Formatos HTTPS requieren PO Token; descarga 403 |
| Cookies + `tv` | `The page needs to be reloaded` |
| Cookies + `web_embedded` | **Descarga correcta** (probado con sección de 2 s) |

Por eso el flujo actual reintenta con `web_embedded` cuando el cliente por
defecto falla con 403 o solo devuelve imágenes. No se descargó nada en el
teléfono: todas las pruebas de descarga se hicieron en el Codespace.

## 6. Limitaciones y riesgos actuales

- **Facturación/cuota:** la cuenta `Michel30006` no puede arrancar su Codespace
  por HTTP 402. Se usa la otra cuenta o se reutiliza un Codespace existente.
- **Repo privado:** `michel3000006` no puede crear un Codespace desde
  `Michel30006/todus-lite`; solo reutiliza los suyos.
- **YouTube:** puede cambiar el reto o exigir PO Token; el fallback
  `web_embedded` no está garantizado para todos los vídeos.
- **ToDus:** el envío no se reanuda; si se corta, hay que reiniciar desde el
  principio. La descarga sí se reanuda.
- **Caché:** si el envío falla, la descarga se conserva para reintentar; tras
  un envío correcto se borra del Codespace.
- **Privacidad:** las cookies equivalen a la sesión de Google; no deben
  publicarse. El receptor no autentica al emisor.
- **Regla del usuario:** no descargar nada en el teléfono; usar solo el
  Codespace para descargas y pruebas reales.

## 7. Pendientes

1. Repetir una prueba real completa **después** del cambio de limpieza para
   confirmar que `descargas/` desaparece y el Codespace queda en `Shutdown`.
2. Probar 720p y enlaces de TikTok/Instagram/Facebook.
3. Decidir si se rota/elimina el secreto antiguo `TDS_COOKIES_B64`.
4. Resolver la facturación de `Michel30006` o añadir la otra cuenta como
   colaboradora del repo privado.
5. Opcional: reanudación persistente del envío ToDus.
6. Opcional: nombre legible para el vídeo recibido.

## 8. Cómo retomar

1. Leer este documento y [`CONTINUIDAD.md`](CONTINUIDAD.md).
2. Ejecutar `python3 -m unittest discover -s tests -v` (55 OK).
3. Comprobar `gh codespace list` con cada token; todos deberían estar
   `Shutdown` si no hay una ejecución en curso.
4. No descargar nada en el teléfono; ejecutar `descargar` desde Termux y dejar
   que el Codespace descargue y envíe.
5. No commitear ni publicar tokens, cookies ni el fichero `progreso`.
