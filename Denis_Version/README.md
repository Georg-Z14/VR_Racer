# 🎥 Raspberry Pi 5 Kamera-Streaming-System

Ein vollständiges Kamera-Streaming- und Aufnahme-System für den Raspberry Pi 5 mit Web-Interface, GPS-Tracking, Account-Verwaltung und automatischem Cloud-Upload.

![Version](https://img.shields.io/badge/version-1.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11-green.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)

---

## 📋 Inhaltsverzeichnis

- [Features](#-features)
- [Systemanforderungen](#-systemanforderungen)
- [Installation](#-installation)
- [Konfiguration](#-konfiguration)
- [Verwendung](#-verwendung)
- [Account-Verwaltung](#-account-verwaltung)
- [Streaming-Modi](#-streaming-modi)
- [Troubleshooting](#-troubleshooting)
- [FAQ](#-faq)

---

## ✨ Features

### 🔐 Account-System
- **Zwei fest definierte Admin-Accounts** (Admin_G, Admin_D)
- **Admin kann neue Accounts erstellen** (Normal-User und weitere Admins)
- **Session-Management**: 2 Stunden für User, unbegrenzt für Admins
- **Sichere Passwort-Speicherung** mit SHA-256 Hashing und Salt

### 📹 Video-Streaming
- **Zwei Streaming-Methoden**:
  - **MJPEG**: Höhere Kompatibilität, alle Browser (500-1000ms Latenz)
  - **WebRTC**: Niedrige Latenz ~100-300ms, beste Qualität
- **Full HD 1920x1080 @ 30fps** (Standard)
- **4K 3840x2160 @ 60fps** (optional aktivierbar)
- **HTTPS-verschlüsselte Übertragung**

### 🎬 Video-Aufnahme
- **MP4-Format mit H.264 Codec**
- **Dateiname**: `recording_DD_MM_YYYY_HH.MM.mp4`
- **Speicher-Check** vor Aufnahme (Warnung bei <15%)
- **Bestätigungs-Dialog** zum Speichern/Löschen
- **Automatischer SFTP-Upload** auf eigenen Server
- **Lokale Datei wird nach 7 Tagen gelöscht**

### 🗺️ GPS-Integration
- **USB-GPS-Empfänger Support** (auskommentiert, aktivierbar)
- **Echtzeit-Positionsanzeige**
- **Routenverfolgung** auf OpenStreetMap
- **GPX-Export** für GPS-Tracks
- **GPS-Daten in Video-Metadaten**

### 📧 Email-Funktion
- **Normal-User können Aufnahmen per Email anfordern**
- **Automatischer Versand über Outlook SMTP**
- **Enthält**: Video, Fahrtzeit, Datum, Route-Screenshot
- **Dankestext mit Benutzername**

### 👥 Benutzerrechte

#### Normal-User können:
- ✅ Live-Stream ansehen
- ✅ GPS-Daten und Route sehen
- ✅ Fahrtzeit anzeigen
- ✅ Aufnahme per Email anfordern

#### Admin kann zusätzlich:
- ✅ Aufnahme starten/stoppen
- ✅ Alle Aufnahmen sehen/herunterladen/löschen
- ✅ Kamera-Einstellungen ändern (Helligkeit, Kontrast, Zoom)
- ✅ Accounts verwalten (erstellen, löschen, ändern)
- ✅ System-Logs einsehen
- ✅ System neu starten/herunterfahren
- ✅ Raspberry Pi IP-Adresse sehen

### 🚀 Autostart
- **systemd Service** für automatischen Start beim Booten
- **Automatischer Neustart** bei Absturz
- **Logging** in separate Dateien

---

## 💻 Systemanforderungen

### Hardware
- **Raspberry Pi 5** (4GB oder 8GB RAM empfohlen)
- **Raspberry Pi Camera Module 3** (oder kompatibel)
- **microSD-Karte**: Minimum 32GB (64GB+ empfohlen)
- **USB-GPS-Empfänger** (optional, z.B. U-blox)
- **Stromversorgung**: USB-C Netzteil mit mindestens 5V/3A

### Software
- **Raspberry Pi OS** (64-bit, Bookworm oder neuer)
- **Python 3.11** oder neuer
- **Internet-Verbindung** für Installation und Updates

### Netzwerk
- **WLAN oder Ethernet**
- **Feste IP-Adresse** empfohlen (über Router-Einstellungen)
- **Port-Freigabe** im Router falls Zugriff von außen gewünscht

---

## 🔧 Installation

### Schritt 1: System vorbereiten

System aktualisieren
sudo apt update
  
sudo apt upgrade -y

Repository klonen oder Dateien kopieren
cd /home/pi
  
mkdir camera_system
  
cd camera_system


### Schritt 2: Automatische Installation

Setup-Script ausführbar machen
chmod +x setup_install.sh
Installation starten (dauert ca. 10-15 Minuten)
sudo bash setup_install.sh


Das Script installiert automatisch:
- ✅ Python 3.11 und alle Abhängigkeiten
- ✅ Picamera2 für Raspberry Pi Kamera
- ✅ Flask Web-Framework
- ✅ GPS-Software (gpsd)
- ✅ Alle Python-Pakete
- ✅ SSL-Zertifikat (selbstsigniert)

### Schritt 3: Kamera aktivieren

Raspberry Pi Konfiguration öffnen
sudo raspi-config

Navigiere zu: 3 Interface Options → I1 Camera → Enable
sudo reboot


### Schritt 4: Dateien kopieren

Kopiere alle Python-Module, Templates und Static-Dateien:

Verzeichnisstruktur:
/home/pi/camera_system/
  ├── main_mjpeg.py           # MJPEG-Version
  ├── main_webrtc.py          # WebRTC-Version
  ├── setup_install.sh        # Installations-Script
  ├── config/
  │   └── config.json         # Konfiguration
  ├── modules/
  │   ├── auth.py
  │   ├── camera.py
  │   ├── gps.py
  │   ├── email_sender.py
  │   ├── sftp_uploader.py
  │   ├── logger.py
  │   └── utils.py
  ├── templates/
  │   ├── login.html
  │   ├── user_dashboard.html
  │   ├── admin.html
  │   └── error.html
  └── static/
  ├── css/
  │   └── style.css
  └── js/
  ├── admin.js
  └── stream.js


### Schritt 5: Service installieren

Service-Installation (wähle MJPEG oder WebRTC)
chmod +x install_services.sh
  sudo bash install_services.sh

Wähle Option 1 (MJPEG) oder 2 (WebRTC)


---

## ⚙️ Konfiguration

### config.json bearbeiten

nano /home/pi/camera_system/config/config.json


### Wichtige Einstellungen:

#### 1. Server-Port (MUSS angepasst werden!)

“server”: {
  “port”: 5000,  // ← ÄNDERE DIESEN PORT!
 “host”: “0.0.0.0”
  }


#### 2. Email-Konfiguration (für Email-Funktion)

“email”: {
  “smtp_server”: “smtp-mail.outlook.com”,
  “smtp_port”: 587,
  “sender_email”: “DEINE-EMAIL@outlook.com”,  // ← ÄNDERN!
 “sender_password”: “DEIN-PASSWORT”          // ← ÄNDERN!
 }


**Wichtig für Outlook:**
- Aktiviere 2-Faktor-Authentifizierung in deinem Microsoft-Account
- Erstelle ein **App-Passwort** unter https://account.microsoft.com/security
- Verwende das App-Passwort (nicht dein normales Passwort!)

#### 3. SFTP-Server (für automatischen Upload)

“sftp”: {
  “enabled”: true,
  “host”: “DEINE-SERVER-IP”,           // ← ÄNDERN!
 “port”: 22,
  “username”: “DEIN-USERNAME”,         // ← ÄNDERN!
 “password”: “DEIN-PASSWORT”,         // ← ÄNDERN!
 “remote_path”: “/uploads/recordings/”
  }


#### 4. GPS aktivieren (optional)

“gps”: {
  “enabled”: true,  // ← Auf true setzen
  “gpsd_host”: “127.0.0.1”,
  “gpsd_port”: 2947
  }


Dann in `modules/gps.py` die auskommentierten Zeilen aktivieren (siehe Kommentare im Code).

#### 5. 4K-Modus aktivieren (optional)
In `modules/camera.py` die 4K-Zeilen auskommentieren:

Suche nach “4K MODUS” und entferne die Kommentare (#)

self.resolution = tuple(self.config‘camera’‘resolution_4k’)  # (3840, 2160)
 self.framerate = self.config‘camera’‘framerate_4k’  # 60


---

## 🚀 Verwendung

### System starten


Manuell starten (für Tests)
cd /home/pi/camera_system
  source venv/bin/activate
  python3 main_mjpeg.py
Oder via Service (empfohlen)
sudo systemctl start camera_mjpeg.service



### Zugriff auf Web-Interface

1. **Finde die IP-Adresse des Raspberry Pi:**

hostname -I

Ausgabe z.B.: 192.168.1.100


2. **Öffne Browser auf einem anderen Gerät im Netzwerk:**

https://192.168.1.100:5000


3. **Akzeptiere SSL-Warnung** (selbstsigniertes Zertifikat)

4. **Login mit Admin-Account:**
   - Benutzername: `Admin_G` oder `Admin_D`
   - Passwort: `admin1234` oder `123456789`

### Standard-Accounts

| Benutzername | Passwort    | Typ   |
|--------------|-------------|-------|
| Admin_G      | admin1234   | Admin |
| Admin_D      | 123456789   | Admin |

**⚠️ WICHTIG:** Diese Passwörter sollten nach dem ersten Login geändert werden!

### Neue Benutzer erstellen (nur Admin)

1. Login als Admin
2. Gehe zu **Admin-Dashboard**
3. Klicke auf Tab **"Benutzer"**
4. Button **"➕ Benutzer erstellen"**
5. Fülle Formular aus:
   - Benutzername
   - Passwort
   - Email (optional)
   - Typ: Normal-User oder Admin
6. Klicke **"Erstellen"**

---

## 📊 Account-Verwaltung

### Account-Typen

#### 👤 Normal-User
- Kann Live-Stream ansehen
- Sieht GPS-Daten und Route
- Kann Aufnahmen per Email anfordern
- **Keine** Aufnahme-Kontrolle
- **Keine** System-Zugriffe
- Session läuft nach 2 Stunden ab

#### 👑 Admin
- **Alle Funktionen** von Normal-User
- Kann Aufnahmen starten/stoppen
- Kann alle Aufnahmen verwalten
- Kann Kamera-Einstellungen ändern
- Kann Benutzer erstellen/löschen
- Sieht System-Logs
- Kann System steuern (Neustart/Herunterfahren)
- **Unbegrenzte Session-Dauer**

### Session-Management

- **Normal-User**: Session läuft nach **2 Stunden** Inaktivität ab
- **Admin**: Session läuft **nie** ab (bis zu manueller Abmeldung)
- Sessions werden in SQLite-Datenbank gespeichert
- Bei Logout wird Session sofort ungültig

### Passwort-Sicherheit

- Passwörter werden **niemals** im Klartext gespeichert
- **SHA-256 Hashing** mit zufälligem Salt (16 Bytes)
- Jedes Passwort hat einen **einzigartigen Salt**
- Timing-sicherer Vergleich verhindert Timing-Attacken

---

## 🎬 Streaming-Modi

### MJPEG-Streaming

**Vorteile:**
- ✅ Funktioniert in **allen Browsern**
- ✅ Einfache Implementierung
- ✅ Keine spezielle Client-Software nötig
- ✅ Geringer CPU-Verbrauch

**Nachteile:**
- ⚠️ Höhere Latenz (500-1000ms)
- ⚠️ Höhere Bandbreite benötigt

**Verwendung:**


sudo systemctl start camera_mjpeg.service



### WebRTC-Streaming

**Vorteile:**
- ✅ **Sehr niedrige Latenz** (~100-300ms)
- ✅ Beste Bildqualität
- ✅ Geringere Bandbreite durch bessere Kompression
- ✅ Peer-to-Peer Verbindung möglich

**Nachteile:**
- ⚠️ Höherer CPU-Verbrauch
- ⚠️ Benötigt modernen Browser
- ⚠️ Komplexere Konfiguration für externe Zugriffe

**Verwendung:**


sudo systemctl start camera_webrtc.service


Stoppe aktuellen Service
sudo systemctl stop camera_mjpeg.service
Starte anderen Service
sudo systemctl start camera_webrtc.service


**⚠️ Wichtig:** Nur **ein** Service kann gleichzeitig laufen!

---

## 🔍 Troubleshooting

### Problem: Kamera nicht gefunden

**Lösung:**


Prüfe ob Kamera erkannt wird
libcamera-hello –list-cameras
Wenn nichts angezeigt wird:
sudo raspi-config
→ Interface Options → Camera → Enable
sudo reboot



### Problem: Service startet nicht

**Lösung:**

Prüfe Service-Status
sudo systemctl status camera_mjpeg.service
Zeige Fehler-Logs
sudo journalctl -u camera_mjpeg.service -n 50
Häufige Fehler:
- Port bereits belegt → Port in config.json ändern
- Kamera nicht aktiviert → siehe oben
- Datei-Berechtigungen → sudo chown -R pi:pi /home/pi/camera_system


### Problem: Keine Verbindung zum Web-Interface

**Lösung:**

1. Prüfe IP-Adresse
hostname -I
2. Prüfe ob Service läuft
sudo systemctl status camera_mjpeg.service
3. Prüfe Firewall (falls aktiviert)
sudo ufw status sudo ufw allow 5000/tcp
4. Teste lokalen Zugriff
curl -k https://localhost:5000


### Problem: SSL-Zertifikat-Warnung

**Das ist normal!** Das System verwendet ein **selbstsigniertes** Zertifikat.

**Lösung:**
- Im Browser: Klicke auf "Erweitert" → "Trotzdem fortfahren"
- Oder installiere ein echtes SSL-Zertifikat (Let's Encrypt)

### Problem: GPS funktioniert nicht

**Lösung:**


1. Prüfe ob gpsd läuft
sudo systemctl status gpsd
2. Teste GPS-Empfang
cgps -s
3. Konfiguriere GPS-Gerät
sudo nano /etc/default/gpsd
Setze: DEVICES=”/dev/ttyUSB0” (oder dein GPS-Gerät)
4. Neustart
sudo systemctl restart gpsd


### Problem: Email-Versand schlägt fehl

**Lösung:**


1. Prüfe config.json
nano /home/pi/camera_system/config/config.json
2. Für Outlook: Verwende APP-PASSWORT, nicht normales Passwort!
https://account.microsoft.com/security
3. Teste SMTP-Verbindung in Python:
python3
		import smtplib
      server = smtplib.SMTP(‘smtp-mail.outlook.com’, 587)
       server.starttls()
        server.login(‘DEINE-EMAIL’, ‘APP-PASSWORT’)
           Wenn Fehler → Passwort falsch oder 2FA nicht aktiviert


### Problem: SFTP-Upload schlägt fehl

**Lösung:**

1. Teste SFTP-Verbindung manuell
sftp USERNAME@SERVER-IP
2. Prüfe Firewall auf Server
Port 22 muss offen sein
3. Prüfe Berechtigungen auf Server
Upload-Verzeichnis muss schreibbar sein
4. Teste mit Python:
    python3
    		import pysftp
         sftp = pysftp.Connection(‘SERVER-IP’, username=‘USER’, password=‘PASS’)
        		Wenn Fehler → Zugangsdaten prüfen


---

## ❓ FAQ

### Kann ich mehrere Kameras gleichzeitig verwenden?

**Nein**, dieses System ist für **eine Kamera** ausgelegt. Für mehrere Kameras müsste man mehrere Instanzen des Systems auf unterschiedlichen Ports laufen lassen.

### Wie ändere ich Admin-Passwörter?

Die Standard-Admin-Accounts (Admin_G, Admin_D) haben **feste Passwörter** im Code (`modules/auth.py`). Um diese zu ändern:

nano /home/pi/camera_system/modules/auth.py

Ändere Zeilen mit “admin1234” und “123456789”

sudo systemctl restart camera_mjpeg.service


### Kann ich von außerhalb meines Netzwerks zugreifen?

**Ja**, aber mit Vorsicht:

1. **Port-Forwarding** im Router einrichten (z.B. Port 5000 → Raspberry Pi IP)
2. **Starkes Passwort** verwenden
3. **DynDNS-Service** nutzen wenn keine feste IP
4. **Besser:** VPN-Verbindung zum Heimnetzwerk

**⚠️ Sicherheitshinweis:** Raspberry Pi direkt im Internet zu exponieren ist **NICHT empfohlen**! Nutze lieber VPN.

### Wie viel Speicherplatz benötigen Aufnahmen?

**Ungefähre Werte** (abhängig von Bewegung im Bild):

- **Full HD (1920x1080 @ 30fps)**: ~150-250 MB pro Minute
- **4K (3840x2160 @ 60fps)**: ~400-600 MB pro Minute

**Empfehlung:** 
- Nutze automatischen SFTP-Upload
- Aktiviere 7-Tage-Cleanup (Standard)
- Verwende 64GB+ SD-Karte

### Wie sichere ich die Aufnahmen?

**Drei Möglichkeiten:**

1. **Automatischer SFTP-Upload** (empfohlen)
   - Konfiguriere SFTP in `config.json`
   - Upload erfolgt automatisch nach jeder Aufnahme
   - Lokale Datei wird nach 7 Tagen gelöscht

2. **Email-Versand**
   - User können Aufnahmen per Email anfordern
   - Gut für einzelne Videos
   - Email-Limit beachten (~25MB)

3. **Manueller Download**
   - Admin kann alle Aufnahmen herunterladen
   - Über Web-Interface: Admin → Aufnahmen → Download

### Kann ich die Kamera-Auflösung ändern?

**Ja!** In `config.json`:

“camera”: { “resolution”: ,  // ← Full HD “framerate”: 30 }


**Verfügbare Auflösungen:**
- 640x480 (VGA)
- 1280x720 (HD)
- 1920x1080 (Full HD) ← Standard
- 3840x2160 (4K) ← Zusätzliche Code-Änderung nötig

### Wie aktiviere ich 4K?

1. Ändere in `config.json`:

“resolution”: , “framerate”: 60


2. In `modules/camera.py` die auskommentierten 4K-Zeilen aktivieren

3. Service neu starten

**⚠️ Beachte:**
- Benötigt mehr CPU-Leistung
- Höherer Speicherverbrauch
- Langsamere Aufnahme-Starts

### Wie kann ich Logs einsehen?

**System-Logs:**

Live-Logs (scrollt automatisch)
sudo journalctl -u camera_mjpeg.service -f
Letzte 100 Zeilen
sudo journalctl -u camera_mjpeg.service -n 100
Nur Fehler
sudo journalctl -u camera_mjpeg.service -p err


**Anwendungs-Logs:**

Error-Log
tail -f /home/pi/camera_system/logs/error.log
Access-Log (wer hat wann zugegriffen)
tail -f /home/pi/camera_system/logs/access.log
System-Log
tail -f /home/pi/camera_system/logs/system.log


**Im Web-Interface:**
- Login als Admin → Tab "Logs"

### Wie deinstalliere ich das System?

1. Stoppe und deinstalliere Service
sudo bash uninstall_services.sh
2. Lösche Dateien (optional)
rm -rf /home/pi/camera_system
3. Entferne Pakete (optional)
sudo apt remove python3-picamera2 gpsd


---

## 📞 Support

Bei Problemen oder Fragen:

1. **Prüfe diese Dokumentation** (insbesondere Troubleshooting)
2. **Schaue in die Logs** (`sudo journalctl -u camera_mjpeg.service -n 50`)
3. **Prüfe GitHub Issues** (falls Repository öffentlich)

---

## 📄 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert.

---

## 👨‍💻 Version

- **Version:** 1.0
- **Datum:** 30.09.2025
- **Python:** 3.11+
- **Raspberry Pi OS:** Bookworm (64-bit)

---

**Viel Erfolg mit deinem Raspberry Pi Kamera-System! 🎥🚀**





