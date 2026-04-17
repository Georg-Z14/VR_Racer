# VR_Racer

## Zielstruktur

```text
VR_Racer/
├── camera_stream.py
├── requirements.txt
├── run_secure_cached.sh
├── server.py
├── Steuerung_VR_Racer/
│   └── Steuerung_OHNE_Shutdown.py
├── static/
│   ├── css/
│   ├── js/
│   └── media/
├── templates/
└── README.md
```

Lokale Dateien wie `.env`, `users.db`, `secret.key` und `venv/` bleiben auf dem Raspberry Pi, werden aber nicht ins Git-Repo committed.

## Raspberry Pi Setup

Systempakete:

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip python3-dev python3-picamera2 bluetooth bluez swig
```

Projektumgebung:

```bash
cd ~/VR_Racer
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements-pi.txt
chmod +x run_secure_cached.sh
```

`--system-site-packages` ist wichtig, damit die virtuelle Umgebung `picamera2` aus Raspberry Pi OS sehen kann.

Auf dem Mac fuer PyCharm nur die plattformneutralen Pakete installieren:

```bash
pip install -r requirements.txt
```

## Cloudflare Tunnel

Der Server laeuft lokal auf Port `8080`. Cloudflare Tunnel stellt die HTTPS-Adresse fuer Apple Vision Pro bereit.

```bash
./run_secure_cached.sh
```

In einem zweiten Terminal:

```bash
cloudflared tunnel --url http://localhost:8080
```

## Apple Vision Pro VR

Im VR-Modus sendet der Server einen kombinierten Stereo-Stream: linke Kamera links im Bild, rechte Kamera rechts im Bild. Die Webseite trennt diesen Stream im WebXR-Renderer wieder pro Auge. Das ist fuer die Vision Pro weiterhin echter `immersive-vr` Modus; Side-by-Side ist nur das Transportformat.

Empfohlene Pi-Einstellungen in `.env` fuer stabile FPS:

```bash
CAMERA_SIZE=960x720
CAMERA_MAX_FPS=30
CAMERA_BUFFER_COUNT=1
CAMERA_QUEUE=0
CAMERA_COLOR_CONVERT=none
```

Wenn die FPS stabil bleiben, kann `CAMERA_SIZE=1280x720` getestet werden. Falls das Bild zu nah wirkt, kann die Vision-Pro-URL testweise mit `?xrDistance=2.8&xrFov=85` geoeffnet werden.

## PS5 Controller

Die Steuerung braucht diese Raspberry-Pi-Pakete aus `requirements-pi.txt`:

- `evdev` fuer `/dev/input/event*`
- `gpiozero` fuer GPIO-Ausgabe
- `lgpio` als GPIO-Pin-Factory auf dem Raspberry Pi

Start:

```bash
cd ~/VR_Racer
source venv/bin/activate
python3 Steuerung_VR_Racer/Steuerung_OHNE_Shutdown.py
```

Falls der Benutzer keine Rechte auf Controller/GPIO hat:

```bash
sudo usermod -aG input,gpio vrracersbs
```

Danach abmelden und neu per SSH einloggen.

Controller einmalig koppeln und vertrauen:

```bash
bluetoothctl
power on
agent on
default-agent
scan on
```

Den PS5-Controller in Pairing-Modus setzen: PS-Taste und Create-Taste halten, bis die LED schnell blinkt. Dann in `bluetoothctl`:

```bash
pair XX:XX:XX:XX:XX:XX
trust XX:XX:XX:XX:XX:XX
connect XX:XX:XX:XX:XX:XX
scan off
quit
```

Wenn `PS5_CONTROLLER_MAC` in `.env` gesetzt ist, nutzt das Steuerungsskript nur diesen Controller.

## Autostart nach Akkuwechsel

Die Services starten nach einem Neustart automatisch:

- `vr-racer-server.service` fuer den WebRTC/App-Server
- `vr-racer-controller.service` fuer die PS5-Controller-Steuerung
- `vr-racer-tunnel.service` fuer den Cloudflare Quick Tunnel

Installation auf dem Raspberry Pi:

```bash
cd ~/VR_Racer
chmod +x scripts/*.sh
./scripts/install_autostart.sh
```

Direkt starten, ohne neu zu booten:

```bash
sudo systemctl start vr-racer-server.service
sudo systemctl start vr-racer-controller.service
sudo systemctl start vr-racer-tunnel.service
```

Status und Logs pruefen:

```bash
systemctl status vr-racer-server.service
systemctl status vr-racer-controller.service
systemctl status vr-racer-tunnel.service

journalctl -u vr-racer-server.service -f
journalctl -u vr-racer-controller.service -f
journalctl -u vr-racer-tunnel.service -f
```

Hinweis: Der Quick Tunnel erzeugt nach einem Neustart normalerweise eine neue `trycloudflare.com` URL. Fuer eine feste URL braucht ihr spaeter einen benannten Cloudflare Tunnel.
