#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

PORT="${PORT:-8080}"
TUNNEL_URL="${VR_RACER_TUNNEL_URL:-http://localhost:${PORT}}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared wurde nicht gefunden. Installiere cloudflared zuerst."
  exit 127
fi

exec cloudflared tunnel --url "$TUNNEL_URL"
