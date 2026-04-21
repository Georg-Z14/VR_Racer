#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_USER="${SUDO_USER:-$(id -un)}"
INSTALL_GROUP="$(id -gn "$INSTALL_USER")"

if [[ ! -d "$PROJECT_DIR/venv" ]]; then
  echo "venv fehlt in $PROJECT_DIR"
  echo "Erstelle es zuerst mit:"
  echo "  python3 -m venv --system-site-packages venv"
  echo "  source venv/bin/activate"
  echo "  pip install -r requirements/pi.txt"
  exit 1
fi

if [[ ! -x "$PROJECT_DIR/run_secure_cached.sh" ]]; then
  chmod +x "$PROJECT_DIR/run_secure_cached.sh"
fi

mkdir -p "$PROJECT_DIR/data"
chmod +x "$PROJECT_DIR/scripts/start_server.sh"
chmod +x "$PROJECT_DIR/scripts/start_controller.sh"
chmod +x "$PROJECT_DIR/scripts/generate_local_https_cert.sh"
chmod +x "$PROJECT_DIR/scripts/install_mediamtx.sh"

if systemctl list-unit-files vr-racer-tunnel.service >/dev/null 2>&1; then
  sudo systemctl disable --now vr-racer-tunnel.service >/dev/null 2>&1 || true
fi
sudo rm -f /etc/systemd/system/vr-racer-tunnel.service

if ! systemctl list-unit-files mediamtx.service >/dev/null 2>&1; then
  echo "MediaMTX ist noch nicht installiert. Installiere MediaMTX..."
  "$PROJECT_DIR/scripts/install_mediamtx.sh"
fi

sudo tee /etc/systemd/system/vr-racer-server.service >/dev/null <<EOF_SERVICE
[Unit]
Description=VR Racer WebRTC Server
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$INSTALL_USER
Group=$INSTALL_GROUP
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/scripts/start_server.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF_SERVICE

sudo tee /etc/systemd/system/vr-racer-controller.service >/dev/null <<EOF_SERVICE
[Unit]
Description=VR Racer PS5 Controller
Wants=bluetooth.service
After=bluetooth.service

[Service]
Type=simple
User=$INSTALL_USER
Group=$INSTALL_GROUP
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/scripts/start_controller.sh
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF_SERVICE

sudo systemctl daemon-reload
sudo systemctl enable vr-racer-server.service
sudo systemctl enable vr-racer-controller.service
if systemctl list-unit-files mediamtx.service >/dev/null 2>&1; then
  sudo systemctl enable mediamtx.service
fi

echo "Autostart installiert."
echo "Starten ohne Neustart:"
if systemctl list-unit-files mediamtx.service >/dev/null 2>&1; then
  echo "  sudo systemctl start mediamtx.service"
fi
echo "  sudo systemctl start vr-racer-server.service"
echo "  sudo systemctl start vr-racer-controller.service"
echo
echo "Status pruefen:"
if systemctl list-unit-files mediamtx.service >/dev/null 2>&1; then
  echo "  systemctl status mediamtx.service"
fi
echo "  systemctl status vr-racer-server.service"
echo "  systemctl status vr-racer-controller.service"
echo
echo "Aufruf im lokalen Netzwerk:"
echo "  https://<pi-ip>:8443"
