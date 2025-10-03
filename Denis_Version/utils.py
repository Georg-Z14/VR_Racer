#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
Hilfsfunktionen-Modul für Raspberry Pi 5 Kamera-Streaming-System
Datei: modules/utils.py
Version: 1.0
Datum: 30.09.2025

Funktionen:
- Speicherplatz-Überprüfung und Warnung bei <15%
- Dateinamen-Generierung mit Zeitstempel
- Zeitformatierung (Deutschland/CEST)
- Screenshot-Erstellung von GPS-Karten
- Dateigrößen-Berechnungen
- System-Informationen (IP-Adresse, Temperatur)
============================================================================
Modul 14 - Hilfsfunktionen 
============================================================================

"""

import os
import shutil
import socket
from datetime import datetime
import pytz
import subprocess
import json
from PIL import Image, ImageDraw, ImageFont
import io
import logging


class SystemUtils:
    """
    Sammlung von Hilfsfunktionen für das Kamera-System.
    """

    def __init__(self, config, logger):
        """
        Initialisiert die Hilfsfunktionen.

        Args:
            config (dict): System-Konfiguration aus config.json
            logger (SystemLogger): Logger-Instanz für Protokollierung
        """
        self.config = config
        self.logger = logger

        # Deutsche Zeitzone für Zeitstempel
        self.timezone = pytz.timezone('Europe/Berlin')

        # Speicher-Warnschwelle aus Config (Standard: 15%)
        self.storage_warning_threshold = config['storage'].get('warning_threshold_percent', 15)

    # ========================================================================
    # SPEICHERPLATZ-VERWALTUNG
    # ========================================================================

    def check_disk_space(self, path="/"):
        """
        Überprüft den verfügbaren Speicherplatz auf einem Laufwerk.

        Args:
            path (str): Pfad zum zu überprüfenden Laufwerk (Standard: Root /)

        Returns:
            dict: Speicher-Informationen
                {
                    'total_gb': float,        # Gesamtspeicher in GB
                    'used_gb': float,         # Belegter Speicher in GB
                    'free_gb': float,         # Freier Speicher in GB
                    'percent_used': float,    # Prozent belegt
                    'percent_free': float,    # Prozent frei
                    'warning': bool           # True wenn unter Warnschwelle
                }
        """
        try:
            # Hole Speicher-Statistiken mit shutil
            stat = shutil.disk_usage(path)

            # Konvertiere Bytes zu Gigabytes
            total_gb = stat.total / (1024 ** 3)
            used_gb = stat.used / (1024 ** 3)
            free_gb = stat.free / (1024 ** 3)

            # Berechne Prozentuale Werte
            percent_used = (stat.used / stat.total) * 100
            percent_free = (stat.free / stat.total) * 100

            # Prüfe ob Warnung notwendig
            warning = percent_free < self.storage_warning_threshold

            storage_info = {
                'total_gb': round(total_gb, 2),
                'used_gb': round(used_gb, 2),
                'free_gb': round(free_gb, 2),
                'percent_used': round(percent_used, 1),
                'percent_free': round(percent_free, 1),
                'warning': warning,
                'warning_threshold': self.storage_warning_threshold
            }

            # Logge Warnung wenn Speicher knapp wird
            if warning:
                self.logger.log_warning(
                    f"SPEICHER-WARNUNG: Nur noch {percent_free:.1f}% frei ({free_gb:.2f} GB)"
                )

            return storage_info

        except Exception as e:
            self.logger.log_error("Fehler beim Prüfen des Speicherplatzes", exception=e)
            return None

    def get_storage_warning_message(self):
        """
        Erstellt eine formatierte Warnung für niedrigen Speicherplatz.

        Returns:
            str: Formatierte Warnmeldung oder None wenn genug Speicher
        """
        storage = self.check_disk_space()

        if storage and storage['warning']:
            return (
                f"⚠️ SPEICHER-WARNUNG\n\n"
                f"Verfügbarer Speicherplatz: {storage['free_gb']} GB ({storage['percent_free']}%)\n"
                f"Warnschwelle: {storage['warning_threshold']}%\n\n"
                f"Bitte alte Aufnahmen löschen oder auf Server hochladen!"
            )
        return None

    def cleanup_old_recordings(self, recordings_path, max_age_days=7):
        """
        Löscht automatisch alte Aufnahmen die älter als X Tage sind.

        Args:
            recordings_path (str): Pfad zum Aufnahmen-Verzeichnis
            max_age_days (int): Maximales Alter in Tagen (Standard: 7)

        Returns:
            tuple: (deleted_count: int, freed_space_mb: float)
        """
        try:
            deleted_count = 0
            freed_space = 0
            current_time = datetime.now()

            # Durchsuche Aufnahmen-Verzeichnis
            for filename in os.listdir(recordings_path):
                file_path = os.path.join(recordings_path, filename)

                # Prüfe nur Dateien (keine Verzeichnisse)
                if not os.path.isfile(file_path):
                    continue

                # Hole Datei-Erstellungszeit
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                file_age = (current_time - file_time).days

                # Lösche wenn älter als max_age_days
                if file_age > max_age_days:
                    file_size = os.path.getsize(file_path)
                    os.remove(file_path)

                    deleted_count += 1
                    freed_space += file_size

                    self.logger.log_info(
                        f"Alte Aufnahme gelöscht: {filename} "
                        f"(Alter: {file_age} Tage)"
                    )

            freed_space_mb = freed_space / (1024 ** 2)

            if deleted_count > 0:
                self.logger.log_info(
                    f"Cleanup abgeschlossen: {deleted_count} Dateien gelöscht, "
                    f"{freed_space_mb:.2f} MB freigegeben"
                )

            return (deleted_count, round(freed_space_mb, 2))

        except Exception as e:
            self.logger.log_error("Fehler beim Cleanup alter Aufnahmen", exception=e)
            return (0, 0.0)

    # ========================================================================
    # DATEINAMEN-GENERIERUNG
    # ========================================================================

    def generate_recording_filename(self, prefix="recording", extension="mp4"):
        """
        Generiert einen Dateinamen für eine Aufnahme mit Zeitstempel.
        Format: recording_DD_MM_YYYY_HH.MM.mp4

        Args:
            prefix (str): Dateinamen-Präfix (Standard: "recording")
            extension (str): Datei-Endung (Standard: "mp4")

        Returns:
            str: Generierter Dateiname
        """
        # Hole aktuelle Zeit in deutscher Zeitzone
        now = datetime.now(self.timezone)

        # Formatiere Zeitstempel: DD_MM_YYYY_HH.MM
        timestamp = now.strftime("%d_%m_%Y_%H.%M")

        # Erstelle Dateinamen
        filename = f"{prefix}_{timestamp}.{extension}"

        return filename

    def generate_full_recording_path(self, prefix="recording"):
        """
        Generiert vollständigen Pfad für eine neue Aufnahme.

        Args:
            prefix (str): Dateinamen-Präfix

        Returns:
            str: Vollständiger Pfad zur Aufnahme-Datei
        """
        # Hole Aufnahmen-Verzeichnis aus Config
        recordings_dir = self.config['recording']['save_path']

        # Stelle sicher dass Verzeichnis existiert
        if not os.path.exists(recordings_dir):
            os.makedirs(recordings_dir, exist_ok=True)

        # Generiere Dateinamen
        filename = self.generate_recording_filename(prefix)

        # Kombiniere zu vollständigem Pfad
        full_path = os.path.join(recordings_dir, filename)

        return full_path

    # ========================================================================
    # ZEITFORMATIERUNG
    # ========================================================================

    def get_current_datetime_formatted(self, format_str="%d.%m.%Y %H:%M:%S"):
        """
        Gibt die aktuelle Zeit formatiert in deutscher Zeitzone zurück.

        Args:
            format_str (str): Gewünschtes Datums-Format (Standard: DD.MM.YYYY HH:MM:SS)

        Returns:
            str: Formatiertes Datum/Zeit
        """
        now = datetime.now(self.timezone)
        return now.strftime(format_str)

    def format_timestamp(self, timestamp, format_str="%d.%m.%Y %H:%M:%S"):
        """
        Formatiert einen Zeitstempel in deutsches Format.

        Args:
            timestamp (datetime): Zu formatierender Zeitstempel
            format_str (str): Gewünschtes Format

        Returns:
            str: Formatierter Zeitstempel
        """
        if not timestamp:
            return "N/A"

        # Konvertiere zu deutscher Zeitzone falls nötig
        if timestamp.tzinfo is None:
            timestamp = self.timezone.localize(timestamp)
        else:
            timestamp = timestamp.astimezone(self.timezone)

        return timestamp.strftime(format_str)

    def get_timezone_info(self):
        """
        Gibt Informationen über die aktuelle Zeitzone zurück.

        Returns:
            dict: Zeitzonen-Informationen
        """
        now = datetime.now(self.timezone)

        return {
            'timezone': str(self.timezone),
            'abbreviation': now.strftime('%Z'),  # CEST oder CET
            'offset': now.strftime('%z'),  # +0200 oder +0100
            'current_time': now.strftime('%d.%m.%Y %H:%M:%S %Z')
        }

    # ========================================================================
    # SYSTEM-INFORMATIONEN
    # ========================================================================

    def get_raspberry_pi_ip(self, interface='wlan0'):
        """
        Holt die IP-Adresse des Raspberry Pi im lokalen Netzwerk.

        Args:
            interface (str): Netzwerk-Interface (Standard: wlan0 für WLAN)
                            Alternativen: eth0 (LAN), wlan1 (2. WLAN)

        Returns:
            str: IP-Adresse oder "Nicht verfügbar"
        """
        try:
            # Methode 1: Über hostname
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)

            # Wenn 127.0.0.1 zurückgegeben wird, verwende alternative Methode
            if ip_address == "127.0.0.1":
                # Methode 2: Über ifconfig/ip addr
                result = subprocess.run(
                    ['hostname', '-I'],
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    # Erste IP-Adresse aus Ergebnis nehmen
                    ip_address = result.stdout.strip().split()[0]

            return ip_address

        except Exception as e:
            self.logger.log_error("Fehler beim Ermitteln der IP-Adresse", exception=e)
            return "Nicht verfügbar"

    def get_all_network_interfaces(self):
        """
        Holt alle Netzwerk-Interfaces mit IP-Adressen.

        Returns:
            dict: Dictionary mit Interface-Namen und IP-Adressen
        """
        interfaces = {}

        try:
            result = subprocess.run(
                ['ip', '-4', 'addr', 'show'],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                current_interface = None

                for line in result.stdout.split('\n'):
                    # Zeile mit Interface-Namen (z.B. "2: wlan0:")
                    if ': ' in line and '<' in line:
                        parts = line.split(': ')
                        if len(parts) >= 2:
                            current_interface = parts[1].split(':')[0]

                    # Zeile mit IP-Adresse (z.B. "inet 192.168.1.100/24")
                    elif 'inet ' in line and current_interface:
                        ip = line.strip().split()[1].split('/')[0]
                        interfaces[current_interface] = ip

        except Exception as e:
            self.logger.log_error("Fehler beim Ermitteln der Netzwerk-Interfaces", exception=e)

        return interfaces

    def get_cpu_temperature(self):
        """
        Holt die CPU-Temperatur des Raspberry Pi.

        Returns:
            float: Temperatur in Grad Celsius oder None bei Fehler
        """
        try:
            # Lese Temperatur aus System-Datei
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = float(f.read().strip()) / 1000.0

            return round(temp, 1)

        except Exception as e:
            self.logger.log_error("Fehler beim Lesen der CPU-Temperatur", exception=e)
            return None

    def get_system_info(self):
        """
        Sammelt alle System-Informationen.

        Returns:
            dict: Umfassende System-Informationen
        """
        info = {
            'hostname': socket.gethostname(),
            'ip_address': self.get_raspberry_pi_ip(),
            'all_interfaces': self.get_all_network_interfaces(),
            'cpu_temp': self.get_cpu_temperature(),
            'storage': self.check_disk_space(),
            'timezone': self.get_timezone_info(),
            'uptime': self._get_system_uptime()
        }

        return info

    def _get_system_uptime(self):
        """
        Holt die System-Uptime (Zeit seit letztem Boot).

        Returns:
            str: Formatierte Uptime oder None
        """
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.read().split()[0])

            # Konvertiere zu Tagen, Stunden, Minuten
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)

            if days > 0:
                return f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"

        except Exception as e:
            self.logger.log_error("Fehler beim Lesen der Uptime", exception=e)
            return None

    # ========================================================================
    # GPS-KARTEN SCREENSHOT
    # ========================================================================

    def create_map_screenshot(self, track_points, output_path, width=800, height=600):
        """
        Erstellt einen Screenshot der GPS-Route für Email-Anhang.
        Verwendet eine vereinfachte Karten-Darstellung.

        Args:
            track_points (list): Liste von GPS-Punkten [{'latitude', 'longitude'}, ...]
            output_path (str): Pfad zur Ausgabe-Bilddatei
            width (int): Bild-Breite in Pixeln
            height (int): Bild-Höhe in Pixeln

        Returns:
            tuple: (success: bool, message: str)
        """
        if not track_points or len(track_points) < 2:
            return (False, "Nicht genug GPS-Punkte für Karten-Screenshot")

        try:
            # Erstelle leeres Bild mit weißem Hintergrund
            img = Image.new('RGB', (width, height), color='white')
            draw = ImageDraw.Draw(img)

            # Berechne Bounds der Route
            lats = [p['latitude'] for p in track_points]
            lons = [p['longitude'] for p in track_points]

            min_lat, max_lat = min(lats), max(lats)
            min_lon, max_lon = min(lons), max(lons)

            # Füge Padding hinzu (5% auf jeder Seite)
            lat_range = max_lat - min_lat
            lon_range = max_lon - min_lon

            min_lat -= lat_range * 0.05
            max_lat += lat_range * 0.05
            min_lon -= lon_range * 0.05
            max_lon += lon_range * 0.05

            # Funktion zum Konvertieren von GPS zu Pixel-Koordinaten
            def gps_to_pixel(lat, lon):
                x = int(((lon - min_lon) / (max_lon - min_lon)) * (width - 40) + 20)
                y = int(((max_lat - lat) / (max_lat - min_lat)) * (height - 40) + 20)
                return (x, y)

            # Zeichne Gitter (vereinfacht)
            grid_color = (220, 220, 220)
            for i in range(1, 10):
                x = int((width / 10) * i)
                y = int((height / 10) * i)
                draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
                draw.line([(0, y), (width, y)], fill=grid_color, width=1)

            # Zeichne Route als Linie
            pixel_points = [gps_to_pixel(p['latitude'], p['longitude']) for p in track_points]

            # Zeichne Linie zwischen allen Punkten
            for i in range(len(pixel_points) - 1):
                draw.line(
                    [pixel_points[i], pixel_points[i + 1]],
                    fill='blue',
                    width=3
                )

            # Markiere Start (grün) und Ende (rot)
            start_point = pixel_points[0]
            end_point = pixel_points[-1]

            # Start-Punkt (grüner Kreis)
            draw.ellipse(
                [start_point[0] - 8, start_point[1] - 8, start_point[0] + 8, start_point[1] + 8],
                fill='green',
                outline='darkgreen',
                width=2
            )

            # End-Punkt (roter Kreis)
            draw.ellipse(
                [end_point[0] - 8, end_point[1] - 8, end_point[0] + 8, end_point[1] + 8],
                fill='red',
                outline='darkred',
                width=2
            )

            # Füge Text-Informationen hinzu
            try:
                # Versuche Standard-Font zu laden
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
            except:
                # Fallback auf Default-Font
                font = ImageFont.load_default()
                font_small = font

            # Titel
            draw.text((10, 10), "GPS Route", fill='black', font=font)

            # Start/Ende Beschriftungen
            draw.text((start_point[0] + 12, start_point[1] - 5), "Start", fill='darkgreen', font=font_small)
            draw.text((end_point[0] + 12, end_point[1] - 5), "Ende", fill='darkred', font=font_small)

            # Koordinaten-Info am unteren Rand
            info_text = f"Start: {track_points[0]['latitude']:.4f}, {track_points[0]['longitude']:.4f}"
            draw.text((10, height - 25), info_text, fill='gray', font=font_small)

            # Speichere Bild
            img.save(output_path, 'PNG')

            self.logger.log_info(f"Karten-Screenshot erstellt: {output_path}")
            return (True, "Karten-Screenshot erstellt")

        except Exception as e:
            self.logger.log_error("Fehler beim Erstellen des Karten-Screenshots", exception=e)
            return (False, f"Fehler: {str(e)}")

    # ========================================================================
    # DATEIGRÖSSEN-FORMATIERUNG
    # ========================================================================

    def format_file_size(self, size_bytes):
        """
        Formatiert Dateigröße in lesbares Format (B, KB, MB, GB).

        Args:
            size_bytes (int): Dateigröße in Bytes

        Returns:
            str: Formatierte Größe (z.B. "15.3 MB")
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.1f} MB"
        else:
            return f"{size_bytes / (1024 ** 3):.2f} GB"

    def get_file_info(self, file_path):
        """
        Holt detaillierte Informationen über eine Datei.

        Args:
            file_path (str): Pfad zur Datei

        Returns:
            dict: Datei-Informationen oder None
        """
        if not os.path.exists(file_path):
            return None

        try:
            stat = os.stat(file_path)

            return {
                'path': file_path,
                'filename': os.path.basename(file_path),
                'size_bytes': stat.st_size,
                'size_formatted': self.format_file_size(stat.st_size),
                'created': datetime.fromtimestamp(stat.st_ctime),
                'modified': datetime.fromtimestamp(stat.st_mtime),
                'created_formatted': self.format_timestamp(datetime.fromtimestamp(stat.st_ctime)),
                'modified_formatted': self.format_timestamp(datetime.fromtimestamp(stat.st_mtime))
            }

        except Exception as e:
            self.logger.log_error(f"Fehler beim Lesen der Datei-Info: {file_path}", exception=e)
            return None


# ============================================================================
# Beispiel-Verwendung (wird nur ausgeführt wenn Datei direkt gestartet wird)
# ============================================================================
if __name__ == "__main__":
    import sys

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from modules.logger import SystemLogger

    # Test-Konfiguration
    config = {
        'storage': {
            'warning_threshold_percent': 15
        },
        'recording': {
            'save_path': '/tmp/recordings/'
        }
    }

    # Erstelle Logger
    logger = SystemLogger("/tmp/test_logs")

    # Erstelle Utils-Instanz
    print("\n=== SystemUtils Test ===")
    utils = SystemUtils(config, logger)

    # Teste Speicherplatz-Check
    print("\n=== Speicherplatz ===")
    storage = utils.check_disk_space()
    if storage:
        print(f"Gesamt: {storage['total_gb']} GB")
        print(f"Frei: {storage['free_gb']} GB ({storage['percent_free']}%)")
        print(f"Warnung: {storage['warning']}")

    # Teste Dateinamen-Generierung
    print("\n=== Dateinamen-Generierung ===")
    filename = utils.generate_recording_filename()
    print(f"Dateiname: {filename}")

    full_path = utils.generate_full_recording_path()
    print(f"Voller Pfad: {full_path}")

    # Teste System-Informationen
    print("\n=== System-Informationen ===")
    sys_info = utils.get_system_info()
    print(f"Hostname: {sys_info['hostname']}")
    print(f"IP-Adresse: {sys_info['ip_address']}")
    print(f"CPU-Temperatur: {sys_info['cpu_temp']}°C")
    print(f"Uptime: {sys_info['uptime']}")

    # Teste Zeitzonen-Info
    print("\n=== Zeitzonen-Info ===")
    tz_info = utils.get_timezone_info()
    print(f"Zeitzone: {tz_info['timezone']}")
    print(f"Aktuelle Zeit: {tz_info['current_time']}")

    # Teste Netzwerk-Interfaces
    print("\n=== Netzwerk-Interfaces ===")
    interfaces = utils.get_all_network_interfaces()
    for interface, ip in interfaces.items():
        print(f"{interface}: {ip}")

    # Teste Karten-Screenshot (mit Test-Daten)
    print("\n=== GPS-Karten-Screenshot ===")
    test_track = [
        {'latitude': 48.1351, 'longitude': 11.5820},
        {'latitude': 48.1360, 'longitude': 11.5830},
        {'latitude': 48.1370, 'longitude': 11.5840},
        {'latitude': 48.1380, 'longitude': 11.5850}
    ]

    success, msg = utils.create_map_screenshot(test_track, "/tmp/test_map.png")
    print(f"Screenshot: {msg}")

    print("\n=== Test abgeschlossen ===")
