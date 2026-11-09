#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$HOME/.config/tds" "$HOME/.config/yt-dlp"

if [[ -n "${TDS_COOKIES_B64:-}" ]]; then
  printf '%s' "$TDS_COOKIES_B64" | base64 -d > "$HOME/.config/tds/cookies.txt"
  chmod 600 "$HOME/.config/tds/cookies.txt"
fi

if [[ ! -x "$HOME/.deno/bin/deno" ]] && command -v curl >/dev/null 2>&1; then
  curl -fsSL https://deno.land/install.sh | sh -s -- -y >/dev/null 2>&1 || true
fi

if [[ -d "$HOME/.deno/bin" ]] && ! grep -q 'HOME/.deno/bin' "$HOME/.bashrc" 2>/dev/null; then
  printf '\nexport PATH="$HOME/.deno/bin:$PATH"\n' >> "$HOME/.bashrc"
fi

if [[ -d "$HOME/.local/bin" ]] && ! grep -q 'HOME/.local/bin' "$HOME/.bashrc" 2>/dev/null; then
  printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.bashrc"
fi

if ! python3 -c 'import yt_dlp_ejs' >/dev/null 2>&1; then
  python3 -m pip install --user -U "yt-dlp[default]" >/dev/null 2>&1 || true
fi

if [[ -f "$HOME/.config/tds/cookies.txt" ]]; then
  {
    printf -- '--cookies %s\n' "$HOME/.config/tds/cookies.txt"
    printf -- '--no-playlist\n'
    if [[ -x "$HOME/.deno/bin/deno" ]]; then
      printf -- '--js-runtimes deno:%s\n' "$HOME/.deno/bin/deno"
    fi
  } > "$HOME/.config/yt-dlp/config"
fi
