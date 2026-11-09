# Continuidad — estado del proyecto para otra IA

> **Léeme primero si retomas este trabajo.**
> Última actualización: **2026-11-08**, al 83 % de contexto agotado.
> Proyecto: `/root/todus-lite`. Todo funciona y está probado salvo la prueba
> definitiva con el teléfono del usuario.

---

## 0. Estado mínimo (30 segundos)

- Reescritura ligera de `kkk` en **Python 3 puro (solo stdlib)**.
- **Emisor** `enviar.py`: pide enlace + número, descarga, codifica con la tabla
  v1 del kkk, fragmenta en tramas `TDS1` y las envía por ToDus (XMPP).
- **Receptor** `receptor.py` / `receptor.sh`: pide número, antepone `53`
  automáticamente, escucha, reensambla y escribe el vídeo en
  `/sdcard/Download` o `recibidos/`.
- **Probado de verdad contra ToDus**: JWT, bind XMPP, 1 trama y 64 KiB
  (14/14, SHA idéntico). Interop con el receptor C++ del kkk: 214 tramas de
  1 MiB, SHA idéntico.
- **35 pruebas unitarias OK** tras los últimos cambios.
- **Pendiente principal**: que el usuario arranque el receptor en su teléfono
  y hacer una prueba real con un vídeo suyo.
- No se ha descargado nada de Internet sin permiso; las pruebas usaron
  `/dev/urandom` y ficheros locales.

---

## 1. Qué pidió el usuario

1. Partir del proyecto `kkk` (en `/root/kkk`) y hacer algo **ligero, autónomo
   y funcional**.
2. Que se ejecute por **SSH en un GitHub Codespace**.
3. Que **pida un enlace de vídeo**, lo descargue, lo codifique con el
   algoritmo de `kkk` y lo **envíe por ToDus a un teléfono**.
4. Un **receptor** que permita **cambiar de número** fácilmente y que
   **anteponga automáticamente el `53`**.
5. Documentar todo para que otra IA pueda continuar si se agotan los tokens.
6. **Regla explícita: pedir permiso antes de descargar cualquier cosa.**
   Se ha respetado. Cualquier descarga de un vídeo real debe autorizarla el
   usuario.

Idioma de trabajo: **español**. Estilo: directo, sin rodeos.

---

## 2. Dónde está todo

| Ruta | Qué es |
|---|---|
| `/root/todus-lite/` | Proyecto nuevo (este). |
| `/root/todus-lite/enviar.py` | Emisor interactivo. |
| `/root/todus-lite/receptor.py` | Receptor interactivo en Python. |
| `/root/todus-lite/receptor.sh` | Lanzador: pregunta número, normaliza 53, elige C++ o Python. |
| `/root/todus-lite/tds_lite/table_v1.py` | Tabla v1 exacta + tablas de traducción. |
| `/root/todus-lite/tds_lite/protocol.py` | Núcleo: codificación, tramas, CRC, reensamblado, JID. |
| `/root/todus-lite/tds_lite/todus.py` | JWT, protobuf de auth, cliente XMPP, reintentos/DNS. |
| `/root/todus-lite/tds_lite/download.py` | Descarga HTTP(S) con límite, progreso y SHA-256. |
| `/root/todus-lite/tests/` | 35 pruebas + interop con C++. |
| `/root/todus-lite/docs/` | USO, PROTOCOLO, PRUEBAS, CONTINUIDAD. |
| `/root/kkk/` | Proyecto original (referencia, receptor C++ verificado). |
| `/root/kkk/build/client/tds_receiver` | Receptor C++ usado en interop y opción de `receptor.sh`. |
| `/root/kkk/shared/resources/table_v1.txt` | Tabla original. |
| `/root/kkk/docs/limitaciones.md` | Detalles verificados de ToDus. |
| `/root/kkk/docs/prueba-integral.md` | Prueba integral del kkk. |
| `/tmp/tds_e2e/` | Logs y ficheros de la prueba real de 64 KiB. |
| `/tmp/tests.log`, `/tmp/interop.log` | Últimas ejecuciones de pruebas. |

---

## 3. Qué está hecho (checklist)

- [x] Estructura del proyecto.
- [x] Tabla v1 y verificación de SHA/unicidad.
- [x] Protocolo: codificación, tramas `TDS1`, presupuesto 8192, CRC-32,
      reensamblado tolerante a duplicados y desorden, extensión por magic.
- [x] Normalización de números/JID (8 dígitos → `53`+8; JID completo).
- [x] Auth ToDus: protobuf, JWT, reintentos ante DNS/red.
- [x] Cliente XMPP: TLS directo, SASL PLAIN, bind, sesión, presencia,
      envío, `<tdack>`, bucle lector, reconexión básica.
- [x] Caché de IP y reintentos de resolución en `XmppClient`.
- [x] Descarga HTTP(S) con límite, progreso, SHA-256 y rechazo de HTML.
- [x] Emisor interactivo con `--file`, `--to`, `--from`, `--dry-run`,
      `--max-mib`, `--send-delay-ms`, `--insecure-tls`.
- [x] Receptor interactivo con `--number`, `--out`, `--once`, `--verbose`,
      escritura atómica y SHA-256.
- [x] `receptor.sh` con prompt, normalización y selección C++/Python.
- [x] 35 tests offline.
- [x] Interop real con `tds_receiver` C++ (1 MiB, 214 tramas).
- [x] Prueba real ToDus: 1 trama y 64 KiB con SHA idéntico.
- [x] README, USO, PROTOCOLO, PRUEBAS y este CONTINUIDAD.
- [ ] Prueba real con el teléfono del usuario.
- [ ] Vídeo real de varios MiB.
- [ ] (Opcional) Soporte de enlaces no directos vía `yt-dlp`.
- [ ] (Opcional) Reanudación persistente de envíos.
- [ ] (Opcional) `git init` + push a GitHub.

---

## 4. Decisiones de diseño (y por qué)

1. **Python 3 puro, solo stdlib.** El usuario quiere algo ligero que corra en
   un Codespace por SSH sin compilar ni instalar. Nada de PostgreSQL ni
   Servidores A/B del kkk.
2. **Reutilizar el protocolo del kkk tal cual.** Garantiza interoperabilidad
   con el receptor C++ ya verificado y evita re-descubrir ToDus.
3. **Números por defecto del kkk** (`58799457` emisor, `58548838` receptor)
   porque son los que se usaron en las pruebas del kkk.
4. **El `53` se antepone en el receptor**, no en el emisor: el usuario pidió
   explícitamente poder cambiar de número y que el prefijo sea automático.
   El emisor también normaliza, por comodidad.
5. **El receptor escribe en `/sdcard/Download`** si existe (teléfono/Termux);
   si no, en `recibidos/`. Escritura atómica (temp + rename) para no dejar
   ficheros a medias.
6. **Receptor C++ opcional** vía `receptor.sh`: si existe el binario del kkk,
   se usa; si no, cae a Python. Así el usuario puede usar lo ya verificado.
7. **Sin secretos en disco.** El JWT se pide en cada ejecución; no se guarda.
8. **Tramas idénticas al kkk**, no un protocolo nuevo. El CRC-32 y el
   reensamblado se hacen igual.
9. **Reintentos agresivos pero acotados** por el DNS intermitente del entorno
   (ver §8).

---

## 5. Detalles técnicos imprescindibles

### 5.1 Constantes

```text
AUTH_URL        https://auth.todus.cu/v2/auth/token
XMPP_HOST       im.todus.cu
XMPP_PORT       5222 (TLS directo, sin STARTTLS)
TODUS_VERSION   2.1.2
MAX_STANZA      8192 bytes UTF-8
SEND_DELAY      120 ms por defecto
ACK_TIMEOUT     15 s
MAX_VIDEO       25 MiB por defecto
Emisor def.     5358799457@im.todus.cu
Receptor def.   5358548838@im.todus.cu
```

### 5.2 Tabla v1

- 256 símbolos únicos; SHA-256 de la concatenación:
  `c6cfa82beb0eabc11bcd1158264d3ec3de152469236f1280703c62cbfb84a26c`.
- No contiene `|`, `<`, `>`, `&`, `"`, `'`.
- 88 símbolos de 1 byte UTF-8, 168 de 2 bytes; media 1.6562.

### 5.3 Trama

```text
TDS1|<job_id>|<transfer_id>|<idx>|<total>|<ver>|<crc32>|<payload>
```

- `job_id`/`transfer_id`: 16 hex (`secrets.token_hex(8)`).
- `crc32`: zlib del payload UTF-8, 8 hex.
- `ver`: `1`.
- Presupuesto con ids de 16: cabecera 66, payload ≤ 8126 bytes UTF-8.
- El corte respeta límites de símbolos UTF-8 (no parte un carácter de 2 bytes).
- El receptor valida CRC y que todos los caracteres estén en la tabla.

### 5.4 Auth

Protobuf de petición: field 1 = `"53"+numero`, field 3 = `"2.1.2"`,
field 2 = password opcional (no usado). Respuesta: field 2 = JWT.

### 5.5 XMPP

TLS directo → `<stream:stream>` → features → SASL PLAIN
(`\0usuario\0JWT`) → reabrir stream → bind clásico con recurso →
sesión → presencia prioridad 10 → mensajes `type='chat'` con `<body>` →
acuse `<tdack mi='...'/>`. ToDus abrevia elementos (`<m>`, `<b>`, `<p>`,
`<ok/>`) y atributos (`t`, `i`, `f`, `o`).

Detalle completo en [`PROTOCOLO.md`](PROTOCOLO.md).

---

## 6. Cómo ejecutar y probar

### 6.1 Pruebas rápidas (sin red, ~1 s)

```bash
cd /root/todus-lite
python3 -m unittest discover -s tests -v
```

Esperado: `Ran 35 tests ... OK`. (El test del receptor imprime su salida en
stdout; es normal, no es un fallo.)

```bash
python3 -m compileall -q tds_lite enviar.py receptor.py tests && echo OK
```

### 6.2 Interop con el receptor C++ del kkk (~5 s)

```bash
cd /root/todus-lite
python3 tests/interop_kkk.py
```

Esperado: `OK: 214 tramas, 1048576 bytes, SHA-256 identico (...)`.
El SHA es aleatorio en cada ejecución.

### 6.3 Dry-run del emisor (sin red)

```bash
python3 enviar.py --file /tmp/tds_e2e/input.bin --to 58548838 --dry-run
```

Esperado: 14 tramas, `DRY-RUN: no se conecta a ToDus ni se envia nada.`

### 6.4 Prueba real sin teléfono (dos cuentas en el Codespace)

```bash
# Terminal 1
python3 -u receptor.py --number 58548838 --out /tmp/recv --once

# Terminal 2
head -c 65536 /dev/urandom > /tmp/entrada.bin
sha256sum /tmp/entrada.bin
python3 -u enviar.py --file /tmp/entrada.bin --to 58548838 --from 58799457
```

Comparar SHA-256. Tarda ~10-20 s en 14 tramas. **Nota:** el receptor debe
estar ya escuchando; `--once` sale tras reconstruir.

### 6.5 Prueba definitiva (la que falta)

1. El usuario ejecuta en su teléfono (Termux):
   `python3 receptor.py` (o `./receptor.sh`).
2. Escribe el número del teléfono (8 dígitos; el 53 es automático).
3. Espera `LISTO. Esperando tramas TDS1...`.
4. En el Codespace: `python3 enviar.py` y pasa un enlace **directo** a un
   vídeo pequeño (1-5 MiB) o un fichero local con `--file`.
5. Comparar SHA-256 en ambos lados.

**Antes de descargar un vídeo real, pedir permiso al usuario** (regla suya).

---

## 7. Evidencia de las pruebas (2026-11-08)

- **35 tests OK** (`Ran 35 tests in 0.547s`), tras los últimos cambios de red.
- **Interop C++**: 214 tramas, 1 MiB, SHA
  `acdd86c760e689c00b2ca64a9c83acbcba1fc2a48027f84933ffbc2cd1e130a0`,
  RC=0.
- **ToDus real, 1 trama**: 25 bytes, job `036c30e9c597737f`, SHA
  `b0a96be9eb206925ef79c1ed005a8f8c567c25b528b1ee68fc0aa1df8691fd91`,
  acuse OK.
- **ToDus real, 64 KiB**: 14/14 tramas, job `48cf8057b2ff8aba`, SHA
  `bcadffcd9fb12b5d622881393eba3b4e244a77724bffc36fcda7917f964f8d7f`,
  idéntico al receptor.
- **JWT real**: 165 caracteres, prefijo `eyJhbGciOiJI...`.
- **Bind real**: `5358799457@im.todus.cu/tds-lite-test`, cierre limpio.
- Logs: `/tmp/tds_e2e/`.

Detalle en [`PRUEBAS.md`](PRUEBAS.md).

---

## 8. Problemas conocidos y mitigaciones

| Problema | Estado |
|---|---|
| DNS intermitente (`Name or service not known`, `Connection timed out`) | Mitigado: `fetch_token` reintenta 4 veces con backoff 1.5 s; `_resolve()` reintenta 3 veces; caché de IP; `connect_with_retry` 3 intentos; el bucle de envío solo reconecta si la conexión está caída; backoff del receptor acotado a 15 s. |
| El receptor debe arrancar antes que el emisor | Documentado; el emisor espera 5 s (`--start-delay`). No hay handshake. |
| Pérdida de acuses → reintentos | El emisor reintenta la misma trama; el receptor tolera duplicados. |
| La app Android de ToDus puede “robar” los mensajes | La presencia con prioridad 10 ayuda; si no, cerrar la app o usar otra cuenta. |
| Enlaces HTML/YouTube | Rechazados; haría falta `yt-dlp` (pendiente opcional). |
| Sin reanudación persistente | Si el emisor muere, hay que reenviar desde el principio. El receptor tolera duplicados. |
| El test del receptor imprime en stdout | Cosmético; se puede capturar con `contextlib.redirect_stdout` si molesta. |
| `docs/PRUEBAS.md` tenía un SHA fijo del interop | Corregido: ahora aclara que es aleatorio por ejecución. |

---

## 9. Pendientes priorizados

1. **Prueba definitiva en el teléfono** (requiere al usuario). Es lo único
   que falta para validar el caso real.
2. **Vídeo real de 1-5 MiB** por ToDus (con permiso del usuario para
   descargarlo). Medir tiempo y tasa.
3. Revisar el README con el usuario (nombres de carpetas, números, licencia).
4. (Opcional) `yt-dlp` para enlaces de YouTube/TikTok, con permiso explícito
   para instalar/descargar.
5. (Opcional) Reanudación: guardar tramas/estado en disco para no reenviar
   todo si se corta.
6. (Opcional) `git init`, `.gitignore` ya existe, y push a un repo del
   usuario (solo si lo pide).
7. (Opcional) Empaquetar para Termux (script de instalación, instrucciones).

---

## 10. Registro cronológico

1. Exploración de `/root/kkk`: protocolo, tabla v1, framing, auth, XMPP,
   receptor C++. Documentos `limitaciones.md` y `prueba-integral.md`.
2. Creación de `/root/todus-lite` con la estructura y `table_v1.py`.
3. `protocol.py`: codificación/decodificación, tramas, CRC, reensamblado,
   JID, presupuesto 8192.
4. `todus.py`: protobuf, JWT, parser XMPP, TLS/SASL/bind, envío, tdack,
   presencia, bucle lector.
5. `download.py` y `enviar.py` interactivo.
6. `receptor.py` interactivo con escritura atómica.
7. Tests: 35 OK.
8. Interop con C++: 1 MiB, 214 tramas, SHA idéntico.
9. Verificación real de JWT y bind XMPP; corrección de carrera en
   `_sock` None.
10. Prueba real ToDus: 1 trama y 64 KiB, SHA idéntico.
11. Reintentos de `fetch_token`, caché de IP/reintentos en `_open_socket`,
    reconexión solo si está caída, backoff del receptor a 15 s.
12. `--dry-run` añadido y probado (64 KiB → 14 tramas).
13. `receptor.sh` creado; normalización probada con `/bin/echo`.
14. README, USO, PROTOCOLO, PRUEBAS y CONTINUIDAD escritos.
15. README corregido (`cd to dus-lite` → `cd todus-lite`).
16. Re-ejecución final: 35 tests OK, interop 214 tramas OK, compileall OK.

---

## 11. Cómo retomar si se agotan los tokens

1. Lee este archivo entero.
2. Ejecuta las pruebas de §6.1 y §6.2 para confirmar que el estado sigue sano.
3. Pregunta al usuario si quiere hacer ya la prueba en el teléfono (§6.5).
4. No descargues vídeos ni instales nada sin su permiso.
5. Si algo falla, revisa `/tmp/tds_e2e/`, `/tmp/tests.log` y
   `/tmp/interop.log`; el código de red está en `tds_lite/todus.py`.
6. Mantén el estilo: español, respuestas cortas, sin dependencias externas
   salvo autorización.

---

## 12. Preferencias y restricciones del usuario

- **Pedir permiso antes de descargar cualquier cosa.** Incluye vídeos,
  binarios, dependencias y repositorios.
- Quiere **ligero**: evitar frameworks, bases de datos y compilación.
- Quiere **cambiar el número del receptor fácilmente** y que el `53` se
  anteponga solo.
- Documentación en español, pensada para otra IA.
- No commitear ni publicar nada sin que lo pida.

---

## 13. Secretos

- No hay tokens, contraseñas ni claves en el proyecto.
- El JWT se obtiene en cada ejecución y solo vive en memoria.
- Los números por defecto son los de prueba del kkk y están en el código;
  cámbialos si el usuario usa otros.
