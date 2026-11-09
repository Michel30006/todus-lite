#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$HOME/.config/tds" "$HOME/.config/yt-dlp"

if [[ -n "${TDS_COOKIES_B64:-}" ]]; then
  printf '%s' "$TDS_COOKIES_B64" | base64 -d > "$HOME/.config/tds/cookies.txt"
  chmod 600 "$HOME/.config/tds/cookies.txt"
fi

if [[ -f "$HOME/.config/tds/cookies.txt" ]]; then
  {
    printf -- '--cookies %s\n' "$HOME/.config/tds/cookies.txt"
    printf -- '--no-playlist\n'
  } > "$HOME/.config/yt-dlp/config"
fi
