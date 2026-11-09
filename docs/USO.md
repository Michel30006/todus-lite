# Guía de uso

## 0. Resumen del flujo

```text
Telefono (receptor)                     Codespace (emisor)
-------------------                     -------------------
python3 receptor.py                     python3 enviar.py
  pide numero (53 automatico)             pide enlace del video
  conecta a ToDus                         pide numero destino
  "LISTO. Esperando..."                   descarga el video
        ^                                 lo codifica a texto
        |                                 conecta a ToDus
        +-------- tramas TDS1 <-----------+ envia las tramas
  reensambla y escribe el video
  muestra SHA-256
```

El receptor se queda esperando ficheros nuevos. El emisor termina cuando ha
enviado y recibido el acuse de todas las tramas.

## 0.1 Comando rápido `descargar` (Termux)

La forma más simple. En el teléfono, una sola vez:

```bash
ln -sf /root/todus-lite/descargar /usr/local/bin/descargar
gh auth login -h github.com
gh auth refresh -h github.com -s codespace
```

Después:

```bash
descargar
```

El comando:

1. Pide la **URL del vídeo**.
2. Pide el **número destino** (8 dígitos; el 53 es automático).
3. Arranca el receptor local con ese número y espera a `LISTO`.
4. Conecta al Codespace (lo arranca si está parado).
5. Descarga el vídeo con `yt-dlp`/cookies y lo envía por ToDus.
6. Espera a que el receptor escriba el fichero y muestra el SHA-256.

El vídeo queda en `/sdcard/Download`.

- Por defecto el teléfono que ejecuta `descargar` es el receptor. Si envías a
  **otro teléfono**, usa `descargar --remoto`; el otro teléfono debe tener el
  receptor abierto.
- Si ya hay un receptor con otro número, el script avisa y no envía.
- `--remoto` evita arrancar el receptor local.
- Variables: `TDS_CODESPACE`, `TODUS_SENDER`, `TDS_MAX_MIB`, `TDS_OUT_DIR`.
- Autenticación no interactiva opcional:
  ```bash
  mkdir -p ~/.config/todus-lite
  printf '%s' 'ghp_TU_TOKEN' > ~/.config/todus-lite/gh_token
  chmod 600 ~/.config/todus-lite/gh_token
  ```
  El token necesita permiso de **Codespaces** (y `repo` si el repo es privado).

## 1. Requisitos

- Python 3.10 o superior (probado con 3.14).
- Conexión a Internet que permita salir a `auth.todus.cu` y `im.todus.cu:5222`.
- No hace falta `pip install`: todo usa la biblioteca estándar.
- En el teléfono (Termux): `pkg install python` si no está instalado.
- `gh` (GitHub CLI) autenticado para el comando `descargar` y el Codespace.

## 2. Preparar el receptor en el teléfono

### Opción A — receptor Python (recomendado)

Copia la carpeta `todus-lite` al teléfono (por git, `scp`, o Termux) y entra en
ella:

```bash
cd ~/todus-lite
python3 receptor.py
```

Escribe el número del teléfono. Ejemplos:

| Escribes | Se usa |
|---|---|
| `58548838` | `5358548838@im.todus.cu` |
| `5358548838` | `5358548838@im.todus.cu` |
| `+53 5854 8838` | `5358548838@im.todus.cu` |
| `5358548838@im.todus.cu` | igual |

Cuando veas `LISTO. Esperando tramas TDS1...`, déjalo abierto.

### Opción B — binario C++ del kkk

Si ya tienes `tds_receiver` compilado o copiado al teléfono:

```bash
cd ~/todus-lite
TDS_RECEIVER_BIN=/ruta/a/tds_receiver ./receptor.sh
```

`receptor.sh` pregunta el número, antepone el 53 y lanza el binario con
`--watch`. También lo usa automáticamente si encuentra
`../kkk/build/client/tds_receiver`.

### Opción C — JID completo

Si quieres usar una cuenta concreta, escribe el JID completo
(`5358548838@im.todus.cu`); no se modifica.

## 3. Ejecutar el emisor en el Codespace

Conéctate por SSH a tu Codespace y entra en la carpeta:

```bash
cd ~/todus-lite   # o la ruta donde esté el proyecto
python3 enviar.py
```

El script pregunta:

```text
Enlace del video: https://servidor.com/video.mp4
Numero de telefono destino (sin 53 si es de 8 digitos) [58548838]:
```

- Puede ser un enlace **directo** (`.mp4`) o una página de **YouTube**,
  TikTok, Instagram, Facebook, X/Twitter o Vimeo (se usa `yt-dlp`).
- El número destino puede ser de 8 dígitos; el 53 se añade solo.
- El emisor por defecto es `58799457`. Cámbialo con `TODUS_SENDER` o `--from`.

Salida esperada:

```text
Conectando a ToDus como 5358799457@im.todus.cu ...
Conectado como 5358799457@im.todus.cu/tds-lite-sender
Destino: 5358548838@im.todus.cu
Esperando 5 s para que el receptor este escuchando...
Enviadas 14/14 (100.0%) 1.0 tramas/s

ENVIO COMPLETO
  ...
```

### 3.1 YouTube y cookies

YouTube exige cookies de una sesión iniciada y, desde 2026, un runtime
JavaScript (**Deno**) con el solver **EJS**. En el Codespace del proyecto ya
está todo instalado por `.devcontainer`:

- `yt-dlp` + `yt-dlp-ejs` (pip)
- `deno` en `~/.deno/bin/deno`
- `~/.config/yt-dlp/config` con `--cookies` y `--js-runtimes`
- cookies en `~/.config/tds/cookies.txt` (permisos `600`)

El emisor usa esas cookies automáticamente. Si quieres usar otro fichero:

```bash
python3 enviar.py --cookies /ruta/cookies.txt
# o
TDS_COOKIES_FILE=/ruta/cookies.txt python3 enviar.py
```

El fichero debe estar en formato **Netscape** y contener cookies de
`.youtube.com` (`SID`, `HSID`, `SSID`, `APISID`, `SAPISID`, `LOGIN_INFO`,
`__Secure-*`). Para exportarlas desde el navegador se puede usar la extensión
"Get cookies.txt LOCALLY".

Si YouTube cambia y falla, actualiza:

```bash
python3 -m pip install --user -U "yt-dlp[default]"
```

y renueva las cookies.

## 4. Cambiar el número del receptor

No hay que tocar código:

1. En el teléfono, ejecuta `receptor.py` y escribe el nuevo número de 8
   dígitos (o el JID completo).
2. En el Codespace, ejecuta `enviar.py` y escribe el mismo número cuando lo
   pida.

También puedes fijarlo sin preguntas:

```bash
# En el telefono
TDS_NUMBER=55123456 ./receptor.sh

# En el Codespace
python3 enviar.py --to 55123456
```

El prefijo `53` se añade automáticamente si escribes 8 dígitos.

## 5. Cambiar la cuenta emisora

```bash
TODUS_SENDER=55123456 python3 enviar.py
# o
python3 enviar.py --from 55123456
```

La cuenta emisora debe poder autenticarse en ToDus con solo el número (como
los números de prueba del kkk). Si ToDus empieza a exigir contraseña, el error
se mostrará al conectar.

## 6. Opciones útiles del emisor

```bash
python3 enviar.py --help

# Enviar un fichero local (sin descargar)
python3 enviar.py --file video.mp4 --to 58548838

# Solo descargar/codificar y ver el plan (no conecta a ToDus)
python3 enviar.py --file video.mp4 --to 58548838 --dry-run

# Limitar a 10 MiB
python3 enviar.py --max-mib 10

# Cambiar la pausa entre tramas (ms)
python3 enviar.py --send-delay-ms 200

# Usar un JWT ya obtenido (evita pedirlo y los timeouts de auth)
TODUS_TOKEN=... python3 enviar.py
# o
python3 enviar.py --token ...

# Cookies de YouTube
python3 enviar.py --cookies ~/.config/tds/cookies.txt

# No verificar TLS (solo pruebas de laboratorio)
python3 enviar.py --insecure-tls
```

## 7. Opciones útiles del receptor

```bash
python3 receptor.py --help

# Salir tras reconstruir el primer fichero
python3 receptor.py --once

# Directorio de salida concreto
python3 receptor.py --out /sdcard/Download

# Ver por qué se rechaza una trama
python3 receptor.py --verbose
```

Por defecto el receptor escribe en `/sdcard/Download` si existe; si no, en
`recibidos/` junto al proyecto. Al terminar muestra el SHA-256 para que lo
compares con el del emisor.

## 8. Dejar el receptor en segundo plano (Termux)

```bash
nohup python3 -u receptor.py > receptor.log 2>&1 &
tail -f receptor.log
```

Para detenerlo:

```bash
pkill -f receptor.py
```

## 9. Tiempos orientativos

| Vídeo | Tramas | Envío aprox. (120 ms + acuse) |
|---:|---:|---:|
| 64 KiB | 14 | ~10-20 s |
| 1 MiB | 214 | ~1-2 min |
| 5 MiB | ~1074 | ~5-8 min |
| 25 MiB | ~5370 | ~15-25 min |

El tiempo real depende del acuse de ToDus y de la red. Si se pierde una trama,
el emisor la reintenta; el receptor tolera duplicados.

## 10. Problemas frecuentes

| Síntoma | Causa / solución |
|---|---|
| `auth/token no accesible: ... name resolution` | DNS intermitente. El código reintenta y cachea la IP. Espera o vuelve a ejecutar. |
| `auth/token no accesible: timed out` | Red intermitente (también pasa en Codespace). Reintenta; si persiste, obtén un JWT aparte y pásalo con `TODUS_TOKEN`. |
| YouTube solo devuelve imágenes / `n challenge` | Falta Deno o EJS. Ejecuta `.devcontainer/setup.sh` y comprueba `~/.config/yt-dlp/config`. |
| `Sign in to confirm you're not a bot` | Cookies caducadas o ausentes. Renueva `~/.config/tds/cookies.txt`. |
| `No hay sesion valida de GitHub...` | Ejecuta una vez `gh auth login -h github.com` y `gh auth refresh -h github.com -s codespace`. |
| `No encuentro el Codespace ...` | Revisa `gh codespace list` y ajusta `TDS_CODESPACE` si cambió el nombre. |
| `Ya hay un receptor local con el numero ...` | Cierra el receptor anterior (`pkill -f receptor.py`) o usa `descargar --remoto`. |
| `Requested format is not available` | El selector de formato no encontró vídeo; actualiza `yt-dlp` y revisa las cookies. |
| El receptor no recibe nada | Se lanzó el emisor antes que el receptor. Reinicia el emisor después de ver `LISTO`. |
| El receptor no recibe y la app ToDus sí | La app Android puede estar conectada a la misma cuenta. Ciérrala o usa otra cuenta/recurso. |
| `el enlace devolvio HTML` | No es un enlace directo. Usa la URL del fichero `.mp4`. |
| `la descarga supera el limite` | Ajusta `MAX_VIDEO_BYTES` o `--max-mib`. |
| SHA-256 distinto | Revisa que el receptor muestre el mismo hash que el emisor; si no, repite el envío. |
| `SASL PLAIN rechazado` | El JWT caducó o la cuenta ya no admite login solo con número. Vuelve a ejecutar (pide JWT nuevo). |
| Se corta a mitad | El emisor reintenta tramas; si termina, vuelve a ejecutarlo desde el principio (el receptor tolera duplicados). |
| `Address already in use` | No ocurre: el cliente no abre puertos locales; solo conexiones salientes. |

## 11. Privacidad y buenas prácticas

- No publiques tokens ni el contenido de los vídeos.
- Los números por defecto son los de prueba del kkk; cámbialos por los tuyos.
- El receptor no verifica la identidad del emisor. No lo uses con datos
  sensibles.
- Cierra la sesión del receptor cuando no lo uses (`Ctrl-C`).
