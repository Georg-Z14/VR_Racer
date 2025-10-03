#!/bin/bash
# ============================================================================
# Setup-Script für Raspberry Pi 5 Kamera-Streaming-System
# Automatische Installation aller benötigten Abhängigkeiten
# Ausführung: sudo bash setup_install.sh
# ============================================================================
# Modul 1 - Setup-Script
# ============================================================================


echo "======================================================================="
echo "  RASPBERRY PI 5 KAMERA-STREAMING-SYSTEM - INSTALLATION"
echo "======================================================================="
echo ""

# Prüfe ob Script als root ausgeführt wird
if [ "$EUID" -ne 0 ]; then
    echo "Bitte führe das Script mit sudo aus: sudo bash setup_install.sh"
    exit 1
fi

echo "[1/8] System-Pakete werden aktualisiert..."
# Aktualisiere alle System-Pakete auf die neueste Version
apt-get update
apt-get upgrade -y

echo "[2/8] Python 3.11 und Entwicklungstools werden installiert..."
# Installiere Python 3.11, pip (Paketmanager) und venv (Virtual Environment)
apt-get install -y python3-pip python3-venv python3-dev

echo "[3/8] Picamera2 und Kamera-Abhängigkeiten werden installiert..."
# Picamera2 ist die offizielle Bibliothek für Raspberry Pi Kameras
# libcamera ist die Low-Level Kamera-Schnittstelle
apt-get install -y python3-picamera2 python3-libcamera libcamera-apps

echo "[4/8] OpenCV für Bildverarbeitung wird installiert..."
# OpenCV ermöglicht erweiterte Bildverarbeitung und Computer Vision
apt-get install -y python3-opencv python3-numpy

echo "[5/8] GPS-Modul Unterstützung wird installiert..."
# gpsd ist der GPS-Daemon für Linux-Systeme
# gpsd-clients enthält Tools zum Testen der GPS-Verbindung
apt-get install -y gpsd gpsd-clients python3-gps

echo "[6/8] FFmpeg für Video-Encoding wird installiert..."
# FFmpeg ist notwendig für H.264 Video-Encoding in MP4-Container
apt-get install -y ffmpeg libavcodec-dev libavformat-dev

echo "[7/8] OpenSSL für SSL-Zertifikate wird installiert..."
# OpenSSL wird für die Erstellung selbstsignierter HTTPS-Zertifikate benötigt
apt-get install -y openssl

echo "[8/8] Python Virtual Environment wird erstellt..."
# Erstelle isolierte Python-Umgebung im Projektverzeichnis
cd /home/pi/camera_system
python3 -m venv venv

# Aktiviere die Virtual Environment
source venv/bin/activate

echo "Python-Pakete werden installiert (dies kann einige Minuten dauern)..."

# Flask: Web-Framework für den Server
# flask-login: Session-Management für Benutzer-Logins
# flask-cors: Cross-Origin Resource Sharing für API-Zugriffe
pip install --upgrade pip
pip install flask==3.0.0 flask-login==0.6.3 flask-cors==4.0.0

# Picamera2: Offizielle Raspberry Pi Kamera-Bibliothek
pip install picamera2

# OpenCV für erweiterte Bildverarbeitung
pip install opencv-python==4.8.1.78

# aiortc: WebRTC-Implementierung für Python (niedrige Latenz)
# aiohttp: Asynchroner HTTP-Server für WebRTC-Signaling
pip install aiortc==1.6.0 aiohttp==3.9.0

# pytz: Zeitzonen-Unterstützung für Deutschland (CEST)
pip install pytz==2023.3

# Pillow: Bildbearbeitung (für Screenshots der Karte)
pip install Pillow==10.1.0

# GPS-Bibliotheken
# gpsd-py3: Python-Interface für GPS-Daemon
# geopy: Geocoding und Distanz-Berechnungen
pip install gpsd-py3==0.3.0 geopy==2.4.0

# folium: OpenStreetMap-Integration für Karten
pip install folium==0.15.0

# SFTP für Upload auf eigenen Server
# pysftp: High-Level SFTP-Client
# paramiko: SSH-Protokoll-Implementierung
pip install pysftp==0.2.9 paramiko==3.4.0

echo ""
echo "SSL-Zertifikat wird erstellt..."
# Erstelle selbstsigniertes SSL-Zertifikat für HTTPS
# Gültig für 365 Tage, 4096-Bit RSA-Verschlüsselung
mkdir -p /home/pi/camera_system/ssl
openssl req -x509 -newkey rsa:4096 -nodes \
    -out /home/pi/camera_system/ssl/cert.pem \
    -keyout /home/pi/camera_system/ssl/key.pem \
    -days 365 \
    -subj "/C=DE/ST=Bayern/L=Munich/O=RaspberryPi/CN=raspberrypi.local"

# Setze korrekte Berechtigungen für SSL-Dateien
chmod 600 /home/pi/camera_system/ssl/key.pem
chmod 644 /home/pi/camera_system/ssl/cert.pem

echo ""
echo "Verzeichnisstruktur wird erstellt..."
# Erstelle alle notwendigen Verzeichnisse mit korrekten Berechtigungen
mkdir -p /home/pi/camera_system/recordings
mkdir -p /home/pi/camera_system/logs
mkdir -p /home/pi/camera_system/config
mkdir -p /home/pi/camera_system/database
mkdir -p /home/pi/camera_system/gps_tracks
mkdir -p /home/pi/camera_system/modules
mkdir -p /home/pi/camera_system/templates
mkdir -p /home/pi/camera_system/static/css
mkdir -p /home/pi/camera_system/static/js

# Setze Besitzer auf pi-Benutzer
chown -R pi:pi /home/pi/camera_system

echo ""
echo "======================================================================="
echo "  INSTALLATION ERFOLGREICH ABGESCHLOSSEN!"
echo "======================================================================="
echo ""
echo "Nächste Schritte:"
echo "1. Konfiguriere config/config.json mit deinen Einstellungen"
echo "2. Kopiere alle Python-Module in das Verzeichnis"
echo "3. Starte das System mit:"
echo "   sudo systemctl start camera_mjpeg.service"
echo ""
echo "Logs findest du unter: /home/pi/camera_system/logs/"
echo ""
