#!/usr/bin/env bash
# Lanzador del receptor. Pide el numero y antepone el 53 automaticamente.
#
# Usa el binario C++ verificado del kkk si lo encuentra (TDS_RECEIVER_BIN o
# ../kkk/build/client/tds_receiver); si no, usa receptor.py (Python, sin deps).
#
# Variables:
#   TDS_NUMBER         numero (si falta, se pregunta; def. 58548838)
#   TDS_OUT_DIR        directorio de salida
#   TDS_RECEIVER_BIN   ruta al tds_receiver C++ del kkk
#   TDS_TOKEN          JWT ya obtenido (opcional)
#   TDS_SERVER_A_URL   Servidor A del kkk para verificar/confirmar (opcional)
#   TDS_INTERNAL_TOKEN token interno de A/B (opcional)
#
# Ejemplos:
#   ./receptor.sh
#   TDS_NUMBER=55123456 ./receptor.sh
#   TDS_RECEIVER_BIN=/ruta/tds_receiver ./receptor.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_NUMBER="58548838"

NUMBER="${TDS_NUMBER:-}"
if [[ -z "$NUMBER" ]]; then
  read -r -p "Numero de telefono de este receptor (8 digitos o 53+8) [$DEFAULT_NUMBER]: " NUMBER
  NUMBER="${NUMBER:-$DEFAULT_NUMBER}"
fi

# Normaliza: quita espacios, guiones y el '+' inicial.
NUMBER="${NUMBER//[[:space:]]/}"
NUMBER="${NUMBER//-/}"
NUMBER="${NUMBER#+}"

if [[ "$NUMBER" == *@* ]]; then
  LOCAL="${NUMBER%%@*}"
elif [[ "$NUMBER" =~ ^[0-9]{8}$ ]]; then
  LOCAL="53$NUMBER"
elif [[ "$NUMBER" =~ ^53[0-9]{8}$ ]]; then
  LOCAL="$NUMBER"
else
  echo "Numero no valido: '$NUMBER' (usa 8 digitos, 53+8 digitos o un JID)" >&2
  exit 1
fi

OUT_DIR="${TDS_OUT_DIR:-}"
if [[ -z "$OUT_DIR" ]]; then
  if [[ -d /sdcard/Download ]]; then
    OUT_DIR="/sdcard/Download"
  elif [[ -d /storage/emulated/0/Download ]]; then
    OUT_DIR="/storage/emulated/0/Download"
  else
    OUT_DIR="$ROOT/recibidos"
  fi
fi
mkdir -p "$OUT_DIR"

CANDIDATE="${TDS_RECEIVER_BIN:-$ROOT/../kkk/build/client/tds_receiver}"
if [[ -x "$CANDIDATE" ]]; then
  echo "Receptor C++ del kkk: $CANDIDATE"
  echo "  numero: $NUMBER -> $LOCAL@im.todus.cu"
  echo "  salida: $OUT_DIR"
  ARGS=(--xmpp-user "$LOCAL" --watch "$OUT_DIR" --out-dir "$OUT_DIR")
  [[ -n "${TDS_TOKEN:-}" ]] && ARGS+=(--xmpp-token "$TDS_TOKEN")
  [[ -n "${TDS_SERVER_A_URL:-}" ]] && ARGS+=(--server-a "$TDS_SERVER_A_URL")
  [[ -n "${TDS_INTERNAL_TOKEN:-}" ]] && ARGS+=(--internal-token "$TDS_INTERNAL_TOKEN")
  exec "$CANDIDATE" "${ARGS[@]}"
fi

echo "Receptor Python (no se encontro el binario C++ del kkk)"
exec python3 -u "$ROOT/receptor.py" --number "$LOCAL" --out "$OUT_DIR" "$@"
