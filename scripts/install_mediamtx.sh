#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_SRC="$PROJECT_DIR/configs/mediamtx.yml"
INSTALL_DIR="/opt/mediamtx"
CONFIG_DIR="/etc/mediamtx"
CERT_DIR="$CONFIG_DIR/certs"
CERT_SRC="$PROJECT_DIR/certs/vrracer.crt"
KEY_SRC="$PROJECT_DIR/certs/vrracer.key"
SERVICE_FILE="/etc/systemd/system/mediamtx.service"
VERSION="${MEDIAMTX_VERSION:-latest}"

if [[ ! -f "$CONFIG_SRC" ]]; then
  echo "Config nicht gefunden: $CONFIG_SRC" >&2
  exit 1
fi

case "$(uname -m)" in
  aarch64|arm64)
    MEDIAMTX_ARCH="arm64"
    ;;
  armv7l|armhf)
    MEDIAMTX_ARCH="armv7"
    ;;
  x86_64|amd64)
    MEDIAMTX_ARCH="amd64"
    ;;
  *)
    echo "Nicht unterstuetzte Architektur: $(uname -m)" >&2
    exit 1
    ;;
esac

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if [[ "$VERSION" == "latest" ]]; then
  DOWNLOAD_URL="$(python3 - "$MEDIAMTX_ARCH" <<'PY'
import json
import sys
import urllib.request

arch = sys.argv[1]
with urllib.request.urlopen("https://api.github.com/repos/bluenviron/mediamtx/releases/latest", timeout=30) as response:
    release = json.load(response)

suffix = f"linux_{arch}.tar.gz"
for asset in release.get("assets", []):
    name = asset.get("name", "")
    if name.endswith(suffix):
        print(asset["browser_download_url"])
        break
else:
    raise SystemExit(f"Kein MediaMTX Release-Asset fuer {suffix} gefunden")
PY
)"
else
  RELEASE_TAG="$VERSION"
  if [[ "$RELEASE_TAG" != v* ]]; then
    RELEASE_TAG="v$RELEASE_TAG"
  fi
  DOWNLOAD_URL="https://github.com/bluenviron/mediamtx/releases/download/${RELEASE_TAG}/mediamtx_${RELEASE_TAG}_linux_${MEDIAMTX_ARCH}.tar.gz"
fi

echo "Lade MediaMTX: $DOWNLOAD_URL"
curl -fL "$DOWNLOAD_URL" -o "$TMP_DIR/mediamtx.tar.gz"
tar -xzf "$TMP_DIR/mediamtx.tar.gz" -C "$TMP_DIR"

sudo install -d "$INSTALL_DIR" "$CONFIG_DIR"
sudo install -m 0755 "$TMP_DIR/mediamtx" "$INSTALL_DIR/mediamtx"
sudo ln -sf "$INSTALL_DIR/mediamtx" /usr/local/bin/mediamtx
sudo install -m 0644 "$CONFIG_SRC" "$CONFIG_DIR/mediamtx.yml"

if [[ ! -f "$CERT_SRC" || ! -f "$KEY_SRC" ]]; then
  echo "Lokales HTTPS-Zertifikat fehlt. Erzeuge es jetzt..."
  "$PROJECT_DIR/scripts/generate_local_https_cert.sh"
fi

sudo install -d "$CERT_DIR"
sudo install -m 0644 "$CERT_SRC" "$CERT_DIR/vrracer.crt"
sudo install -m 0600 "$KEY_SRC" "$CERT_DIR/vrracer.key"

sudo tee "$SERVICE_FILE" >/dev/null <<EOF_SERVICE
[Unit]
Description=MediaMTX low-latency WebRTC camera server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/mediamtx /etc/mediamtx/mediamtx.yml
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF_SERVICE

sudo systemctl daemon-reload
sudo systemctl enable mediamtx.service

echo "MediaMTX installiert."
echo "Starten: sudo systemctl start mediamtx.service"
echo "Logs:    journalctl -u mediamtx.service -f"
echo "Player:  https://<pi-ip>:8889/cam"
