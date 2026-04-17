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
sudo apt install -y git python3-venv python3-pip python3-picamera2 bluetooth bluez
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
