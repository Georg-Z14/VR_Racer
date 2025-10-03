#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
GPS-Modul für Raspberry Pi 5 Kamera-Streaming-System
Datei: modules/gps.py
Version: 1.0
Datum: 30.09.2025

Funktionen:
- USB-GPS-Empfänger Integration (auskommentiert, aktivierbar)
- Echtzeit GPS-Positionserfassung
- Route-Tracking mit Zeitstempel
- GPX-Export für GPS-Tracks
- Geschwindigkeits- und Höhenmessung
- Integration mit OpenStreetMap für Kartendarstellung
============================================================================
# MODUL 4 - GPS-MODUL
============================================================================

"""

import time
import threading
from datetime import datetime, timezone
import os
import json
import logging
from collections import deque

# ============================================================================
# GPS-Bibliotheken (werden nur bei aktiviertem GPS benötigt)
# Zum Aktivieren: Kommentare bei den import-Zeilen entfernen
# ============================================================================
try:
    import gpsd

    GPS_AVAILABLE = True
except ImportError:
    GPS_AVAILABLE = False
    print("WARNUNG: gpsd-Bibliothek nicht installiert. GPS-Funktionen deaktiviert.")
    print("Installation: pip install gpsd-py3")

try:
    from geopy.distance import geodesic

    GEOPY_AVAILABLE = True
except ImportError:
    GEOPY_AVAILABLE = False
    print("WARNUNG: geopy-Bibliothek nicht installiert. Distanz-Berechnung deaktiviert.")
    print("Installation: pip install geopy")


class GPSController:
    """
    Hauptklasse für GPS-Steuerung und Route-Tracking.
    Unterstützt USB-GPS-Empfänger über gpsd-Daemon.
    """

    def __init__(self, config, logger):
        """
        Initialisiert den GPS-Controller.

        Args:
            config (dict): GPS-Konfiguration aus config.json
            logger (SystemLogger): Logger-Instanz für Protokollierung
        """
        self.config = config
        self.logger = logger

        # GPS-Status
        self.gps_enabled = config['gps'].get('enabled', False)
        self.is_connected = False
        self.current_position = None

        # Route-Tracking
        self.is_tracking = False
        self.track_points = []  # Liste aller GPS-Punkte der aktuellen Route
        self.track_start_time = None
        self.total_distance = 0.0  # Gesamte zurückgelegte Strecke in Kilometern

        # Thread für kontinuierliche GPS-Updates
        self.gps_thread = None
        self.gps_thread_running = False
        self.track_interval = config['gps'].get('track_interval_seconds', 5)

        # gpsd-Verbindungsparameter
        self.gpsd_host = config['gps'].get('gpsd_host', '127.0.0.1')
        self.gpsd_port = config['gps'].get('gpsd_port', 2947)

        # Initialisiere GPS-Verbindung wenn aktiviert
        if self.gps_enabled:
            self.connect_gps()
        else:
            self.logger.log_info("GPS ist deaktiviert (config: gps.enabled = false)")

    def connect_gps(self):
        """
        Stellt Verbindung zum GPS-Daemon (gpsd) her.
        Muss ausgeführt werden wenn GPS aktiviert ist.
        """
        if not GPS_AVAILABLE:
            self.logger.log_warning("GPS-Bibliothek nicht verfügbar. GPS kann nicht aktiviert werden.")
            return False

        try:
            self.logger.log_info(f"Verbinde mit GPS-Daemon: {self.gpsd_host}:{self.gpsd_port}")

            # ================================================================
            # USB-GPS-EMPFÄNGER: Auskommentieren zum Aktivieren
            # ================================================================
            # Verbinde mit gpsd
            # gpsd.connect(host=self.gpsd_host, port=self.gpsd_port)
            #
            # # Warte kurz auf GPS-Fix (Satelliten-Verbindung)
            # time.sleep(2)
            #
            # # Hole erste Position um Verbindung zu testen
            # packet = gpsd.get_current()
            #
            # if packet.mode >= 2:  # Mode 2 = 2D-Fix, Mode 3 = 3D-Fix
            #     self.is_connected = True
            #     self.logger.log_info(f"GPS verbunden: Mode {packet.mode}")
            #     return True
            # else:
            #     self.logger.log_warning("GPS verbunden aber kein Fix (warte auf Satelliten)")
            #     self.is_connected = True
            #     return True
            # ================================================================

            # Für Tests ohne GPS-Hardware: Simulierte Verbindung
            self.logger.log_info("GPS-Modul im Test-Modus (ohne Hardware)")
            self.is_connected = True
            return True

        except Exception as e:
            self.logger.log_error("Fehler beim Verbinden mit GPS", exception=e)
            self.is_connected = False
            return False

    def get_current_position(self):
        """
        Holt die aktuelle GPS-Position.

        Returns:
            dict: GPS-Daten oder None wenn kein Fix
                {
                    'latitude': float,      # Breitengrad
                    'longitude': float,     # Längengrad
                    'altitude': float,      # Höhe in Metern
                    'speed': float,         # Geschwindigkeit in km/h
                    'heading': float,       # Richtung in Grad (0-360)
                    'timestamp': str,       # ISO-Format Zeitstempel
                    'satellites': int,      # Anzahl Satelliten
                    'fix_quality': int      # GPS-Fix Qualität (0-3)
                }
        """
        if not self.is_connected:
            return None

        try:
            # ================================================================
            # USB-GPS-EMPFÄNGER: Auskommentieren zum Aktivieren
            # ================================================================
            # # Hole aktuelles GPS-Paket von gpsd
            # packet = gpsd.get_current()
            #
            # # Prüfe ob GPS-Fix vorhanden (Mode 2 = 2D, Mode 3 = 3D)
            # if packet.mode < 2:
            #     return None
            #
            # # Erstelle GPS-Daten-Dictionary
            # gps_data = {
            #     'latitude': packet.lat,
            #     'longitude': packet.lon,
            #     'altitude': packet.alt if packet.mode == 3 else 0.0,
            #     'speed': packet.hspeed * 3.6 if hasattr(packet, 'hspeed') else 0.0,  # m/s -> km/h
            #     'heading': packet.track if hasattr(packet, 'track') else 0.0,
            #     'timestamp': datetime.now(timezone.utc).isoformat(),
            #     'satellites': packet.sats if hasattr(packet, 'sats') else 0,
            #     'fix_quality': packet.mode
            # }
            #
            # self.current_position = gps_data
            # return gps_data
            # ================================================================

            # Test-Daten für Entwicklung ohne GPS-Hardware
            # Simuliert eine Position in München, Deutschland
            gps_data = {
                'latitude': 48.1351 + (time.time() % 100) * 0.0001,  # Leichte Bewegung simulieren
                'longitude': 11.5820 + (time.time() % 100) * 0.0001,
                'altitude': 520.0,
                'speed': 45.5,  # km/h
                'heading': 180.0,  # Süd
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'satellites': 8,
                'fix_quality': 3  # 3D-Fix
            }

            self.current_position = gps_data
            return gps_data

        except Exception as e:
            self.logger.log_error("Fehler beim Abrufen der GPS-Position", exception=e)
            return None

    def start_tracking(self):
        """
        Startet das GPS-Route-Tracking.
        Erfasst GPS-Positionen im konfigurierten Intervall.

        Returns:
            tuple: (success: bool, message: str)
        """
        if self.is_tracking:
            return (False, "Route-Tracking läuft bereits")

        if not self.is_connected:
            return (False, "Keine GPS-Verbindung vorhanden")

        try:
            # Initialisiere Tracking-Variablen
            self.track_points = []
            self.track_start_time = datetime.now()
            self.total_distance = 0.0
            self.is_tracking = True

            # Starte GPS-Thread für kontinuierliche Updates
            self.gps_thread_running = True
            self.gps_thread = threading.Thread(target=self._tracking_loop, daemon=True)
            self.gps_thread.start()

            self.logger.log_info(f"GPS-Tracking gestartet (Intervall: {self.track_interval}s)")
            return (True, "GPS-Tracking gestartet")

        except Exception as e:
            self.is_tracking = False
            self.logger.log_error("Fehler beim Starten des GPS-Trackings", exception=e)
            return (False, f"Fehler: {str(e)}")

    def _tracking_loop(self):
        """
        Interne Schleife für kontinuierliches GPS-Tracking.
        Läuft in separatem Thread und erfasst GPS-Punkte im Intervall.
        """
        last_position = None

        while self.gps_thread_running and self.is_tracking:
            try:
                # Hole aktuelle GPS-Position
                current_pos = self.get_current_position()

                if current_pos:
                    # Füge Position zur Track-Liste hinzu
                    track_point = {
                        'latitude': current_pos['latitude'],
                        'longitude': current_pos['longitude'],
                        'altitude': current_pos['altitude'],
                        'speed': current_pos['speed'],
                        'timestamp': current_pos['timestamp'],
                        'time_offset': (datetime.now() - self.track_start_time).total_seconds()
                    }

                    self.track_points.append(track_point)

                    # Berechne Distanz zum letzten Punkt (falls vorhanden)
                    if last_position and GEOPY_AVAILABLE:
                        try:
                            distance = geodesic(
                                (last_position['latitude'], last_position['longitude']),
                                (current_pos['latitude'], current_pos['longitude'])
                            ).kilometers

                            self.total_distance += distance

                        except Exception as e:
                            self.logger.log_debug(f"Fehler bei Distanz-Berechnung: {e}")

                    last_position = current_pos

                # Warte bis zum nächsten Intervall
                time.sleep(self.track_interval)

            except Exception as e:
                self.logger.log_error("Fehler im GPS-Tracking Loop", exception=e)
                time.sleep(self.track_interval)

    def stop_tracking(self):
        """
        Stoppt das GPS-Route-Tracking.

        Returns:
            tuple: (success: bool, message: str, track_stats: dict)
        """
        if not self.is_tracking:
            return (False, "Kein Tracking aktiv", None)

        try:
            # Stoppe Tracking-Thread
            self.gps_thread_running = False
            if self.gps_thread:
                self.gps_thread.join(timeout=5)

            # Berechne Statistiken
            track_end_time = datetime.now()
            duration = track_end_time - self.track_start_time

            track_stats = {
                'start_time': self.track_start_time.isoformat(),
                'end_time': track_end_time.isoformat(),
                'duration_seconds': int(duration.total_seconds()),
                'duration_formatted': self._format_duration(duration.total_seconds()),
                'total_distance_km': round(self.total_distance, 2),
                'point_count': len(self.track_points),
                'avg_speed_kmh': round(
                    (self.total_distance / (duration.total_seconds() / 3600))
                    if duration.total_seconds() > 0 else 0, 1
                )
            }

            self.is_tracking = False

            self.logger.log_info(
                f"GPS-Tracking gestoppt: {track_stats['total_distance_km']} km, "
                f"{track_stats['point_count']} Punkte"
            )

            return (True, "GPS-Tracking gestoppt", track_stats)

        except Exception as e:
            self.is_tracking = False
            self.logger.log_error("Fehler beim Stoppen des GPS-Trackings", exception=e)
            return (False, f"Fehler: {str(e)}", None)

    def get_tracking_stats(self):
        """
        Gibt aktuelle Tracking-Statistiken zurück (während Tracking läuft).

        Returns:
            dict: Aktuelle Statistiken oder None wenn kein Tracking aktiv
        """
        if not self.is_tracking or not self.track_start_time:
            return None

        duration = (datetime.now() - self.track_start_time).total_seconds()

        return {
            'is_tracking': True,
            'duration_seconds': int(duration),
            'duration_formatted': self._format_duration(duration),
            'total_distance_km': round(self.total_distance, 2),
            'point_count': len(self.track_points),
            'current_position': self.current_position
        }

    def export_gpx(self, output_path, track_name=None):
        """
        Exportiert die aufgezeichnete Route als GPX-Datei.
        GPX ist das Standard-Format für GPS-Tracks (kompatibel mit Google Earth, etc.)

        Args:
            output_path (str): Pfad zur Ausgabe-GPX-Datei
            track_name (str): Optional - Name des Tracks

        Returns:
            tuple: (success: bool, message: str)
        """
        if not self.track_points:
            return (False, "Keine Track-Punkte zum Exportieren vorhanden")

        try:
            # Erstelle Verzeichnis falls nicht vorhanden
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            # Erstelle GPX-XML-Struktur
            if not track_name:
                track_name = f"Track_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            gpx_content = self._generate_gpx_xml(track_name)

            # Schreibe GPX-Datei
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(gpx_content)

            file_size = os.path.getsize(output_path)

            self.logger.log_info(f"GPX-Track exportiert: {output_path} ({file_size} Bytes)")
            return (True, f"GPX-Datei erstellt: {len(self.track_points)} Punkte")

        except Exception as e:
            self.logger.log_error("Fehler beim Exportieren der GPX-Datei", exception=e)
            return (False, f"Fehler: {str(e)}")

    def _generate_gpx_xml(self, track_name):
        """
        Generiert GPX-XML-Inhalt aus den Track-Punkten.

        Args:
            track_name (str): Name des Tracks

        Returns:
            str: GPX-XML als String
        """
        # GPX-Header
        gpx = '<?xml version="1.0" encoding="UTF-8"?>\n'
        gpx += '<gpx version="1.1" creator="RaspberryPi Camera System" '
        gpx += 'xmlns="http://www.topografix.com/GPX/1/1">\n'

        # Metadaten
        gpx += '  <metadata>\n'
        gpx += f'    <name>{track_name}</name>\n'
        gpx += f'    <time>{datetime.now(timezone.utc).isoformat()}</time>\n'
        gpx += '  </metadata>\n'

        # Track
        gpx += '  <trk>\n'
        gpx += f'    <name>{track_name}</name>\n'
        gpx += '    <trkseg>\n'

        # Track-Punkte
        for point in self.track_points:
            gpx += f'      <trkpt lat="{point["latitude"]}" lon="{point["longitude"]}">\n'
            gpx += f'        <ele>{point["altitude"]}</ele>\n'
            gpx += f'        <time>{point["timestamp"]}</time>\n'

            if point.get('speed'):
                gpx += f'        <extensions><speed>{point["speed"]}</speed></extensions>\n'

            gpx += '      </trkpt>\n'

        # GPX-Footer
        gpx += '    </trkseg>\n'
        gpx += '  </trk>\n'
        gpx += '</gpx>'

        return gpx

    def export_json(self, output_path):
        """
        Exportiert die Route als JSON-Datei (für Web-Kartendarstellung).

        Args:
            output_path (str): Pfad zur Ausgabe-JSON-Datei

        Returns:
            tuple: (success: bool, message: str)
        """
        if not self.track_points:
            return (False, "Keine Track-Punkte zum Exportieren vorhanden")

        try:
            # Erstelle Verzeichnis falls nicht vorhanden
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            # Erstelle JSON-Struktur für Leaflet.js (OpenStreetMap)
            track_data = {
                'type': 'FeatureCollection',
                'features': [{
                    'type': 'Feature',
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': [
                            [point['longitude'], point['latitude'], point['altitude']]
                            for point in self.track_points
                        ]
                    },
                    'properties': {
                        'name': f"Track_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        'start_time': self.track_start_time.isoformat() if self.track_start_time else None,
                        'total_distance_km': round(self.total_distance, 2),
                        'point_count': len(self.track_points)
                    }
                }]
            }

            # Schreibe JSON-Datei
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(track_data, f, indent=2, ensure_ascii=False)

            self.logger.log_info(f"JSON-Track exportiert: {output_path}")
            return (True, "JSON-Datei erstellt")

        except Exception as e:
            self.logger.log_error("Fehler beim Exportieren der JSON-Datei", exception=e)
            return (False, f"Fehler: {str(e)}")

    def _format_duration(self, seconds):
        """
        Formatiert Sekunden in lesbares Format (Stunden:Minuten:Sekunden).

        Args:
            seconds (float): Anzahl Sekunden

        Returns:
            str: Formatierte Dauer (z.B. "1h 23m 45s")
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def get_route_bounds(self):
        """
        Berechnet die geografischen Grenzen der Route (für Karten-Zoom).

        Returns:
            dict: Bounds {'min_lat', 'max_lat', 'min_lon', 'max_lon'} oder None
        """
        if not self.track_points:
            return None

        lats = [p['latitude'] for p in self.track_points]
        lons = [p['longitude'] for p in self.track_points]

        return {
            'min_lat': min(lats),
            'max_lat': max(lats),
            'min_lon': min(lons),
            'max_lon': max(lons),
            'center_lat': (min(lats) + max(lats)) / 2,
            'center_lon': (min(lons) + max(lons)) / 2
        }

    def clear_track(self):
        """
        Löscht die aktuelle Track-Historie.

        Returns:
            bool: True wenn erfolgreich
        """
        try:
            self.track_points = []
            self.total_distance = 0.0
            self.track_start_time = None

            self.logger.log_info("GPS-Track gelöscht")
            return True

        except Exception as e:
            self.logger.log_error("Fehler beim Löschen des Tracks", exception=e)
            return False

    def disconnect(self):
        """
        Trennt die GPS-Verbindung und stoppt alle Threads.
        """
        try:
            # Stoppe Tracking falls aktiv
            if self.is_tracking:
                self.stop_tracking()

            # Trenne GPS-Verbindung
            self.is_connected = False

            self.logger.log_info("GPS-Verbindung getrennt")

        except Exception as e:
            self.logger.log_error("Fehler beim Trennen der GPS-Verbindung", exception=e)

    def __del__(self):
        """
        Destruktor - stellt sicher dass GPS sauber beendet wird.
        """
        self.disconnect()


# ============================================================================
# Beispiel-Verwendung (wird nur ausgeführt wenn Datei direkt gestartet wird)
# ============================================================================
if __name__ == "__main__":
    import sys

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from modules.logger import SystemLogger

    # Test-Konfiguration
    config = {
        'gps': {
            'enabled': True,
            'gpsd_host': '127.0.0.1',
            'gpsd_port': 2947,
            'track_interval_seconds': 2
        }
    }

    # Erstelle Logger
    logger = SystemLogger("/tmp/test_logs")

    # Erstelle GPS-Controller
    print("\n=== GPS-Controller Test ===")
    gps = GPSController(config, logger)

    # Teste GPS-Position
    print("\n=== Teste GPS-Position ===")
    position = gps.get_current_position()
    if position:
        print(f"Latitude: {position['latitude']}")
        print(f"Longitude: {position['longitude']}")
        print(f"Altitude: {position['altitude']} m")
        print(f"Speed: {position['speed']} km/h")
        print(f"Satellites: {position['satellites']}")

    # Teste Tracking (10 Sekunden)
    print("\n=== Teste GPS-Tracking (10 Sekunden) ===")
    success, msg = gps.start_tracking()
    print(f"Start: {msg}")

    if success:
        for i in range(5):
            time.sleep(2)
            stats = gps.get_tracking_stats()
            if stats:
                print(f"  {stats['duration_formatted']} - "
                      f"{stats['total_distance_km']} km - "
                      f"{stats['point_count']} Punkte")

        success, msg, final_stats = gps.stop_tracking()
        print(f"\nStop: {msg}")
        if final_stats:
            print(f"Gesamtstrecke: {final_stats['total_distance_km']} km")
            print(f"Durchschnittsgeschwindigkeit: {final_stats['avg_speed_kmh']} km/h")
            print(f"Punkte: {final_stats['point_count']}")

        # Exportiere GPX
        print("\n=== Exportiere GPX ===")
        success, msg = gps.export_gpx("/tmp/test_track.gpx", "Test Track")
        print(f"GPX Export: {msg}")

        # Exportiere JSON
        print("\n=== Exportiere JSON ===")
        success, msg = gps.export_json("/tmp/test_track.json")
        print(f"JSON Export: {msg}")

    print("\n=== Test abgeschlossen ===")
