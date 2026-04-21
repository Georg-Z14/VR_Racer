# VR_Racer

## Zielstruktur

```text
VR_Racer/
├── app/
│   ├── camera_stream.py
│   └── server.py
├── configs/
│   └── mediamtx.yml
├── data/
│   ├── secret.key
│   └── users.db
├── requirements/
│   ├── base.txt
│   └── pi.txt
├── run_secure_cached.sh
├── server.py              # Start-Wrapper fuer app/server.py
├── scripts/
│   ├── generate_local_https_cert.sh
│   ├── install_autostart.sh
│   ├── install_mediamtx.sh
│   ├── start_controller.sh
│   └── start_server.sh
├── Steuerung_VR_Racer/
│   └── Steuerung_stable.py
├── static/
│   ├── css/
│   ├── js/
│   └── media/
├── templates/
└── README.md
```

Lokale Dateien wie `.env`, `data/users.db`, `data/secret.key` und `venv/` bleiben auf dem Raspberry Pi, werden aber nicht ins Git-Repo committed.
Als Vorlage fuer neue Installationen dient `.env.example`.

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
pip install -r requirements/pi.txt
cp .env.example .env
chmod +x run_secure_cached.sh
```

`--system-site-packages` ist wichtig, damit die virtuelle Umgebung `picamera2` aus Raspberry Pi OS sehen kann.

Auf dem Mac fuer PyCharm nur die plattformneutralen Pakete installieren:

```bash
pip install -r requirements/base.txt
```

## Lokales HTTPS ohne Cloudflare

Fuer Apple Vision Pro/WebXR wird HTTPS benoetigt. Fuer niedrige Latenz sollte der Fahrbetrieb aber lokal im WLAN laufen, nicht ueber Cloudflare Tunnel.

```bash
cd ~/VR_Racer
./scripts/generate_local_https_cert.sh
```

Das erzeugt:

```text
certs/vrracer.crt
certs/vrracer.key
```

Die `.env` nutzt danach standardmaessig:

```bash
PORT=8443
HTTPS_ENABLED=1
HTTPS_CERT_FILE=certs/vrracer.crt
HTTPS_KEY_FILE=certs/vrracer.key
```

Server starten:

```bash
./run_secure_cached.sh
```

Aufrufen:

```text
https://<pi-ip>:8443
```

Wichtig: Das Zertifikat `certs/vrracer.crt` muss auf der Vision Pro als vertrauenswuerdig installiert werden. Sonst blockiert Safari/WebXR weiterhin oder zeigt Zertifikatswarnungen.

## Apple Vision Pro / Kinoansicht

Die aktuelle Vision-Pro-Ansicht nutzt eine Mono-/Kinoansicht mit genau einer Kamera. Der Kamera-Stream kommt ausschliesslich von MediaMTX.

Die Kamera wird nicht mehr in `.env` konfiguriert, sondern in `configs/mediamtx.yml`:

```bash
rpiCameraCamID: 0
rpiCameraWidth: 640
rpiCameraHeight: 480
rpiCameraFPS: 30
rpiCameraBitrate: 2000000
```

Wenn FPS und Latenz stabil bleiben, kann danach `rpiCameraWidth: 960`, `rpiCameraHeight: 540` und `rpiCameraBitrate: 2500000` getestet werden. `1280x720` sollte erst getestet werden, wenn die niedrigeren Profile konstant fluessig laufen. Falls das Bild zu nah wirkt, kann die Vision-Pro-URL testweise mit `?xrDistance=2.8&xrFov=85` geoeffnet werden.

## MediaMTX Stream

MediaMTX stellt den Kamera-Stream direkt als WebRTC/WHEP bereit. Die Python-App bleibt fuer Login, UI, Steuerung und Vision-Pro/Kinoansicht zustaendig, oeffnet die Kamera aber nicht mehr selbst.

Installation auf dem Raspberry Pi:

```bash
cd ~/VR_Racer
chmod +x scripts/install_mediamtx.sh
./scripts/install_mediamtx.sh
sudo systemctl start mediamtx.service
```

Logs pruefen:

```bash
journalctl -u mediamtx.service -f
```

Direkter MediaMTX-Test im Browser:

```text
https://<pi-ip>:8889/cam
```

Die VR_Racer-App nutzt standardmaessig MediaMTX:

```bash
STREAM_BACKEND=mediamtx
MEDIAMTX_WEBRTC_URL=
```

Wenn `MEDIAMTX_WEBRTC_URL` leer bleibt, nutzt der Browser automatisch denselben Host wie die App:

```text
https://<pi-ip>:8889/cam/whep
```

Nach Aenderungen an `.env` den Python-Server neu starten:

```bash
sudo systemctl restart vr-racer-server.service
```

## PS5 Controller

Die Steuerung braucht diese Raspberry-Pi-Pakete aus `requirements/pi.txt`:

- `evdev` fuer `/dev/input/event*`
- `gpiozero` fuer GPIO-Ausgabe
- `lgpio` als GPIO-Pin-Factory auf dem Raspberry Pi

Start:

```bash
cd ~/VR_Racer
source venv/bin/activate
python3 Steuerung_VR_Racer/Steuerung_stable.py
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

Die Steuerung fragt beim Start nicht interaktiv nach einem Eingabegeraet, damit der systemd-Dienst nicht haengen bleibt. Falls automatisch das falsche Eingabegeraet gewaehlt wird, kann in `.env` optional `CONTROLLER_DEVICE_PATH=/dev/input/...` gesetzt werden.

Controller abmelden:

```text
PS + Options
```

Falls die PS-Taste nicht als normales Linux-Event ankommt:

```text
Create/Share + Options
```

Die Tastenkombination stoppt Motor und Servo sofort, trennt den Controller wenn moeglich per Bluetooth und beendet den Controller-Dienst sauber. Wieder aktivieren:

```bash
sudo systemctl start vr-racer-controller.service
```

## Autostart nach Akkuwechsel

Die Services starten nach einem Neustart automatisch:

- `mediamtx.service` fuer den Low-Latency-Kamerastream, wenn MediaMTX installiert ist
- `vr-racer-server.service` fuer den HTTPS-App-Server
- `vr-racer-controller.service` fuer die PS5-Controller-Steuerung

Der alte Cloudflare-Tunnel wird vom Installer deaktiviert und nicht mehr eingerichtet. Die App wird lokal im WLAN ueber die Pi-IP aufgerufen.

Installation auf dem Raspberry Pi:

```bash
cd ~/VR_Racer
chmod +x scripts/*.sh
./scripts/install_autostart.sh
```

Der Installer deaktiviert den alten Cloudflare-Tunnel, installiert MediaMTX falls noetig und aktiviert alle benoetigten lokalen Services.

Direkt starten, ohne neu zu booten:

```bash
sudo systemctl start mediamtx.service
sudo systemctl start vr-racer-server.service
sudo systemctl start vr-racer-controller.service
```

Status und Logs pruefen:

```bash
systemctl status mediamtx.service
systemctl status vr-racer-server.service
systemctl status vr-racer-controller.service

journalctl -u mediamtx.service -f
journalctl -u vr-racer-server.service -f
journalctl -u vr-racer-controller.service -f
```

Aufruf im lokalen Netzwerk:

```text
https://<pi-ip>:8443
```

Auf dem Pi selbst geht auch:

```text
https://localhost:8443
```
