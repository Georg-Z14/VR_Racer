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
  echo "  pip install -r requirements-pi.txt"
  exit 1
fi

if [[ ! -x "$PROJECT_DIR/run_secure_cached.sh" ]]; then
  chmod +x "$PROJECT_DIR/run_secure_cached.sh"
fi

chmod +x "$PROJECT_DIR/scripts/start_server.sh"
chmod +x "$PROJECT_DIR/scripts/start_controller.sh"
chmod +x "$PROJECT_DIR/scripts/start_cloudflare_tunnel.sh"

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
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF_SERVICE

sudo tee /etc/systemd/system/vr-racer-tunnel.service >/dev/null <<EOF_SERVICE
[Unit]
Description=VR Racer Cloudflare Quick Tunnel
Wants=network-online.target vr-racer-server.service
After=network-online.target vr-racer-server.service

[Service]
Type=simple
User=$INSTALL_USER
Group=$INSTALL_GROUP
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/scripts/start_cloudflare_tunnel.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF_SERVICE

sudo systemctl daemon-reload
sudo systemctl enable vr-racer-server.service
sudo systemctl enable vr-racer-controller.service
sudo systemctl enable vr-racer-tunnel.service

echo "Autostart installiert."
echo "Starten ohne Neustart:"
echo "  sudo systemctl start vr-racer-server.service"
echo "  sudo systemctl start vr-racer-controller.service"
echo "  sudo systemctl start vr-racer-tunnel.service"
echo
echo "Status pruefen:"
echo "  systemctl status vr-racer-server.service"
echo "  systemctl status vr-racer-controller.service"
echo "  systemctl status vr-racer-tunnel.service"
