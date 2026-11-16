# Continuidad — cómo retomar el proyecto

> **Léeme primero si retomas este trabajo.**
> Última actualización: **2026-11-16**.
> Proyecto: `/root/todus-lite`, repo privado
> `https://github.com/Michel30006/todus-lite`.
> Estado detallado y evidencia: [`ESTADO.md`](ESTADO.md).

## 0. Estado mínimo

- Reescritura ligera de `kkk` en **Python 3 puro (solo stdlib)**.
- Flujo completo probado: **YouTube → Codespace → ToDus → teléfono**.
- **55 pruebas offline OK**.
- Última prueba real: YouTube `YahWlZoKHkY` en **480p**, 29.536.718 bytes,
  5990/5990 tramas, SHA-256 idéntico, fichero
  `/sdcard/Download/95c6350cf2b98fe7.mp4`.
- El emisor descarga en el **Codespace**, no en el teléfono. El usuario
  prohíbe descargar o instalar cosas en el teléfono.
- Multi-cuenta: prueba tokens en orden, salta cuentas con HTTP 402 y reutiliza
  cualquier Codespace existente si no hay uno del repo.
- YouTube: si el cliente por defecto da **403**, reintenta con
  **`web_embedded`**.
- Tras un envío correcto: borra `descargas/` del Codespace y **apaga el
  Codespace** (salvo `--keep`/`TDS_KEEP_CODESPACE=1`).

## 1. Qué hace el proyecto

1. Pide una URL y una calidad (360/480/720).
2. Descarga el vídeo en el Codespace con HTTP o `yt-dlp` + cookies.
3. Codifica cada byte con la tabla v1 del kkk.
4. Fragmenta en tramas `TDS1` de máximo 8192 bytes UTF-8.
5. Envía las tramas por ToDus (XMPP) al número receptor.
6. El receptor reensambla, decodifica y escribe el vídeo en
   `/sdcard/Download` (o `recibidos/`).
7. Emisor y receptor comparan SHA-256.

## 2. Estructura

| Ruta | Qué es |
|---|---|
| `/root/todus-lite/enviar.py` | Emisor interactivo/CLI. |
| `/root/todus-lite/descargar` | Comando Termux: URL + calidad + número, Codespace y envío. |
| `/root/todus-lite/receptor.py` | Receptor Python. |
| `/root/todus-lite/receptor.sh` | Lanzador que normaliza el número y elige C++/Python. |
| `/root/todus-lite/tds_lite/table_v1.py` | Tabla v1 del kkk. |
| `/root/todus-lite/tds_lite/protocol.py` | Codificación, tramas, CRC, reensamblado y JID. |
| `/root/todus-lite/tds_lite/todus.py` | JWT, protobuf de auth, XMPP, reintentos/DNS. |
| `/root/todus-lite/tds_lite/download.py` | HTTP/yt-dlp, calidades, reanudación, validación y fallback de YouTube. |
| `/root/todus-lite/.devcontainer/` | Codespace: sshd, Deno/EJS, yt-dlp, ffmpeg y cookies. |
| `/root/todus-lite/tests/` | 55 pruebas + interop C++. |
| `/root/todus-lite/docs/` | ESTADO, USO, PROTOCOLO, PRUEBAS y este documento. |
| `/root/kkk/` | Proyecto original y receptor C++ de referencia. |

## 3. Funcionalidades actuales

### Protocolo y receptor

- Tabla v1 exacta: 256 símbolos, sin `|` ni especiales XML.
- Trama: `TDS1|job_id|transfer_id|indice|total|version|crc32|payload`.
- CRC-32 (zlib) del payload UTF-8.
- Reensamblado tolerante a duplicados y desorden.
- Normalización: 8 dígitos → `53` + 8; JID completo se respeta.
- Receptor con escritura atómica, `--number`, `--out`, `--once`, `--verbose`.
- `receptor.sh` usa el binario C++ del kkk si existe; si no, Python.
- Interop verificada con el receptor C++ (214 tramas, 1 MiB, SHA idéntico).

### Descarga

- HTTP(S) directo con `Range` y `.part` para reanudar.
- `yt-dlp` para YouTube/TikTok/Instagram/Facebook/X/Vimeo.
- Calidades 360/480/720; **sin límite de tamaño por defecto**.
- Límite opcional con `--max-mib` o `MAX_VIDEO_BYTES`.
- Cookies Netscape, Deno + EJS y configuración persistente.
- Validación de vídeo real (rechaza HTML) y SHA-256.
- Fallback de YouTube: si el cliente por defecto devuelve 403, “solo
  imágenes” o “formato no disponible”, reintenta con `web_embedded`.
- `TDS_YTDLP_PLAYER_CLIENT` permite forzar un cliente concreto.

### Emisor

- `--url`, `--file`, `--to`, `--from`, `--quality`, `--max-mib`,
  `--cookies`, `--cookies-from-browser`, `--token`, `--dry-run`,
  `--send-delay-ms`, `--ack-timeout`, `--retries`, `--frame-bytes`,
  `--resource`, `--insecure-tls`.
- `--delete-after-send`: borra el vídeo descargado tras enviarlo.
- JWT por `TODUS_TOKEN`/`--token` o pedido a ToDus.
- Reintentos de DNS/conexión/tramas y reconexión XMPP.

### `descargar`

- Pide URL, calidad y número; receptor local salvo `--remoto`.
- Rechaza destino == emisor antes de descargar (`--self` lo permite).
- Tokens: `GH_TOKEN` → `~/.config/todus-lite/tokens/*.token|*.txt` →
  `~/.config/todus-lite/gh_token`.
- HTTP 402/facturación: prueba el siguiente token.
- Codespace: usa el del repo; si no, reutiliza cualquier Codespace de la
  cuenta; si no hay y hay acceso al repo, crea uno.
- Auto-arranque, sync tar de `enviar.py` + `tds_lite/*.py`, copia de cookies y
  `.devcontainer/setup.sh`.
- Instala/verifica `yt-dlp`, Deno/EJS y `ffmpeg`.
- Watchdog `TDS_STALL_SECONDS` (def. 300; `0` desactiva).
- Compara SHA-256 emisor/receptor.
- Borra `descargas/` tras envío correcto y apaga el Codespace siempre (salvo
  `--keep`).
- Si el envío falla, conserva la descarga para reintentar; apaga igualmente.

## 4. Cuentas, tokens y Codespaces

Comprobado el 2026-11-16: **todos los Codespaces están en `Shutdown`**.

### `Michel30006`

- Token en `~/.config/todus-lite/gh_token` (600). **Conservar** por indicación
  del usuario.
- Codespace del proyecto: `todus-lite-vpwj76pxrx4phx6wp`.
- Arrancar da **HTTP 402** (`billing issue` / `currently disallowed`).
- El Codespace antiguo `todus-lite-4q6p9jqxv9rxfqpp9` fue eliminado.

### `michel3000006`

- Token en `~/.config/todus-lite/tokens/cuenta2.token` (600).
- **No tiene acceso** al repo privado `Michel30006/todus-lite`.
- Codespaces:
  - `shocking-ghost-p79xx6vx5p95h6v49` (repo `michel3000006/1`): usado en la
    prueba real de 480p; funciona.
  - `miniature-system-jr9xxg6xprj72qvwv` (repo `michel3000006/2`): disponible;
    en una prueba anterior el SSH dio `context deadline exceeded`.

### Cookies

- `~/.config/todus-lite/cookies.txt` (600): 25 cookies `.youtube.com`,
  4137 bytes, filtradas desde `/sdcard/Download/juj.txt`.
- `/sdcard/Download/juj.txt`: export completo, sensible, fuera del repo.
- El secreto antiguo `TDS_COOKIES_B64` (~7972 bytes) no es recuperable; el
  flujo actual copia las cookies locales al Codespace.

## 5. Cómo ejecutar

### Pruebas

```bash
cd /root/todus-lite
python3 -m unittest discover -s tests -v
```

Esperado: `Ran 55 tests ... OK`. El test del receptor imprime su salida en
stdout; es normal.

### Flujo normal en Termux

```bash
descargar
```

Pide URL, calidad y número. Arranca el receptor local, usa el Codespace,
descarga, envía, verifica SHA, borra el vídeo remoto y apaga el Codespace.

Opciones:

```bash
descargar --remoto   # el receptor está en otro teléfono
descargar --keep     # no apagar el Codespace al terminar
descargar --self     # permitir destino == emisor (solo pruebas)
```

### Emisor directo en el Codespace

```bash
cd /tmp/todus-lite
python3 enviar.py --url 'https://youtu.be/...' --to 58548838 \
  --from 58799457 --quality 480 --delay 3 --retries 5 --ack-timeout 20
```

Si se usa `--file`, no se borra el fichero salvo que se pase
`--delete-after-send`; `descargar` lo pasa siempre.

## 6. Problemas conocidos y mitigaciones

| Problema | Estado |
|---|---|
| HTTP 402 al arrancar/crear Codespace | Facturación/cuota de GitHub. `descargar` prueba otro token. Revisar `https://github.com/settings/billing`. |
| Cuenta sin acceso al repo privado | No puede crear Codespace del repo; `descargar` reutiliza cualquier Codespace existente de esa cuenta. |
| YouTube 403 con cliente web | Resuelto con fallback `web_embedded`; si persiste, renovar cookies o forzar `TDS_YTDLP_PLAYER_CLIENT`. |
| `mweb` requiere PO Token | No usar como cliente principal; puede dar 403. |
| `tv` pide recargar la página | Fallo transitorio de YouTube; no es el flujo principal. |
| `context deadline exceeded` en SSH | Fallo transitorio del Codespace; reintentar o usar otro. |
| DNS intermitente de ToDus | Reintentos, caché de IP y reconexión acotada. |
| El receptor debe escuchar antes | No hay handshake; el emisor espera unos segundos. |
| Pérdida de acuses | Reintento de la misma trama; el receptor tolera duplicados. |
| La app Android de ToDus puede robar mensajes | Presencia prioridad 10; cerrar la app o usar otra cuenta. |
| Sin reanudación del envío | La descarga sí se reanuda; el envío ToDus se reinicia. |
| Caché tras fallo de envío | Se conserva para reintentar; se borra tras un envío correcto. |

## 7. Pendientes priorizados

1. Repetir un envío real **después** del cambio de borrado/limpieza y
   confirmar que `descargas/` desaparece y el Codespace queda `Shutdown`.
2. Probar 720p y enlaces de TikTok/Instagram/Facebook.
3. Decidir si se rota/elimina `TDS_COOKIES_B64`.
4. Resolver la facturación de `Michel30006` o añadir `michel3000006` como
   colaboradora del repo privado.
5. Opcional: reanudación persistente del envío ToDus.
6. Opcional: nombre legible para el vídeo recibido.
7. Opcional: empaquetar para Termux.

## 8. Registro cronológico

1. Exploración de `/root/kkk` y del protocolo.
2. Creación de `/root/todus-lite` con tabla v1, protocolo, auth y XMPP.
3. Receptor Python, escritura atómica y lanzador C++/Python.
4. Pruebas offline, interop C++ y ToDus real (1 trama, 64 KiB).
5. YouTube con `yt-dlp` + Deno/EJS + cookies; primer envío real (766 tramas).
6. Comando `descargar` con receptor local, `gh codespace ssh` y `--remoto`.
7. Auto-arranque/auto-apagado del Codespace y sincronización de código.
8. Multi-token, HTTP 402, reutilización de cualquier Codespace, watchdog y
   comparación de SHA.
9. Diagnóstico de YouTube 403 y fallback `web_embedded`.
10. Prueba real 480p (`YahWlZoKHkY`, 5990 tramas, SHA idéntico).
11. Borrado del vídeo remoto tras envío y apagado siempre del Codespace
    (salvo `--keep`); tests y documentación actualizados.

## 9. Restricciones y preferencias del usuario

- **No descargar nada en el teléfono**: las descargas y pruebas reales se
  hacen en el Codespace.
- **Pedir permiso antes de descargar** vídeos, binarios o dependencias.
- Quiere algo **ligero**: sin frameworks, bases de datos ni compilación.
- Cambiar el número del receptor fácilmente y que el `53` se anteponga solo.
- Documentación en español, pensada para otra IA.
- No commitear ni publicar tokens, cookies ni el fichero `progreso`.
- El token de `Michel30006` se conserva de momento; no revocarlo sin pedir.

## 10. Secretos

- No hay tokens, contraseñas ni claves en el repo.
- El JWT se obtiene en cada ejecución y solo vive en memoria.
- Los tokens de GitHub están fuera del repo, con permisos `600`.
- Las cookies están fuera del repo y con permisos `600`.
- Los números por defecto son los de prueba del kkk; cámbialos si hace falta.
