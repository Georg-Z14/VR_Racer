#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
Kamera-Steuerungsmodul für Raspberry Pi 5 Kamera-Streaming-System
Datei: modules/camera.py
Version: 1.0
Datum: 30.09.2025

Funktionen:
- Picamera2-Integration für Raspberry Pi Camera Module (CSI)
- Full HD 1920x1080 @ 30fps (Standard)
- 4K 3840x2160 @ 60fps (auskommentiert, aktivierbar)
- Video-Aufnahme in MP4-Format mit H.264 Codec
- Einstellbare Kamera-Parameter (Helligkeit, Kontrast, Zoom)
- Thread-sicherer Zugriff für parallele Streams
============================================================================
Modul 3 - Kamera-Steuerungsmodul
============================================================================

"""

import time
import threading
import os
from datetime import datetime
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder, Quality
from picamera2.outputs import FileOutput
import io
import logging
from PIL import Image
import numpy as np


class CameraController:
    """
    Hauptklasse für die Steuerung der Raspberry Pi Kamera.
    Unterstützt Live-Streaming und Video-Aufnahmen.
    """

    def __init__(self, config, logger):
        """
        Initialisiert die Kamera mit Konfiguration.

        Args:
            config (dict): Kamera-Konfiguration aus config.json
            logger (SystemLogger): Logger-Instanz für Protokollierung
        """
        self.config = config
        self.logger = logger

        # Kamera-Objekt (wird beim Start initialisiert)
        self.camera = None

        # Streaming-Status
        self.is_streaming = False
        self.stream_lock = threading.Lock()  # Thread-sicherer Zugriff

        # Aufnahme-Status
        self.is_recording = False
        self.recording_start_time = None
        self.current_recording_path = None
        self.encoder = None

        # Frame-Buffer für MJPEG-Streaming
        self.current_frame = None
        self.frame_lock = threading.Lock()

        # Kamera-Einstellungen (werden aus config geladen)
        self.resolution = tuple(config['camera']['resolution'])  # (1920, 1080)
        self.framerate = config['camera']['framerate']  # 30
        self.brightness = config['camera'].get('brightness', 0.0)
        self.contrast = config['camera'].get('contrast', 1.0)
        self.saturation = config['camera'].get('saturation', 1.0)

        # Zoom-Level (1.0 = kein Zoom, 2.0 = 2x Zoom)
        self.zoom_level = 1.0

        # Initialisiere Kamera beim Start
        self.initialize_camera()

    def initialize_camera(self):
        """
        Initialisiert die Picamera2 und startet die Vorschau.
        Diese Methode muss aufgerufen werden bevor die Kamera verwendet wird.
        """
        try:
            self.logger.log_info("Initialisiere Raspberry Pi Kamera...")

            # Erstelle Picamera2-Instanz
            self.camera = Picamera2()

            # Konfiguriere Kamera für Video-Streaming
            # Verwende 'main' Stream für hohe Qualität
            video_config = self.camera.create_video_configuration(
                main={
                    "size": self.resolution,  # (1920, 1080) oder (3840, 2160)
                    "format": "RGB888"  # 24-Bit Farbe
                },
                controls={
                    "FrameRate": self.framerate  # 30 fps oder 60 fps
                }
            )

            # Wende Konfiguration an
            self.camera.configure(video_config)

            # Setze initiale Kamera-Einstellungen
            self._apply_camera_settings()

            # Starte Kamera
            self.camera.start()

            # Warte kurz bis Kamera bereit ist (wichtig für Belichtung/Weißabgleich)
            time.sleep(2)

            self.logger.log_info(
                f"Kamera erfolgreich initialisiert: {self.resolution[0]}x{self.resolution[1]} @ {self.framerate}fps")

            # ================================================================
            # 4K MODUS (auskommentiert) - Zum Aktivieren auskommentieren:
            # ================================================================
            # self.resolution = tuple(self.config['camera']['resolution_4k'])  # (3840, 2160)
            # self.framerate = self.config['camera']['framerate_4k']  # 60
            # video_config_4k = self.camera.create_video_configuration(
            #     main={
            #         "size": self.resolution,
            #         "format": "RGB888"
            #     },
            #     controls={
            #         "FrameRate": self.framerate
            #     }
            # )
            # self.camera.configure(video_config_4k)
            # self.logger.log_info(f"4K Modus aktiviert: {self.resolution[0]}x{self.resolution[1]} @ {self.framerate}fps")
            # ================================================================

        except Exception as e:
            self.logger.log_error("Fehler beim Initialisieren der Kamera", exception=e)
            raise

    def _apply_camera_settings(self):
        """
        Wendet die aktuellen Kamera-Einstellungen an.
        Wird intern bei Änderungen aufgerufen.
        """
        try:
            # Setze Helligkeit (-1.0 bis 1.0, 0.0 = Standard)
            if hasattr(self.camera, 'set_controls'):
                self.camera.set_controls({
                    "Brightness": self.brightness,
                    "Contrast": self.contrast,
                    "Saturation": self.saturation
                })

            # Setze Zoom (ScalerCrop - beschneidet das Bild)
            if self.zoom_level > 1.0:
                # Berechne Crop-Bereich für Zoom
                sensor_size = self.camera.camera_properties['PixelArraySize']
                crop_width = int(sensor_size[0] / self.zoom_level)
                crop_height = int(sensor_size[1] / self.zoom_level)
                crop_x = (sensor_size[0] - crop_width) // 2
                crop_y = (sensor_size[1] - crop_height) // 2

                self.camera.set_controls({
                    "ScalerCrop": (crop_x, crop_y, crop_width, crop_height)
                })

        except Exception as e:
            self.logger.log_warning(f"Fehler beim Anwenden der Kamera-Einstellungen: {e}")

    def set_brightness(self, value):
        """
        Setzt die Helligkeit der Kamera.

        Args:
            value (float): Helligkeitswert (-1.0 bis 1.0, 0.0 = Standard)

        Returns:
            bool: True wenn erfolgreich
        """
        try:
            # Begrenze Wert auf gültigen Bereich
            value = max(-1.0, min(1.0, value))
            self.brightness = value
            self._apply_camera_settings()
            self.logger.log_info(f"Helligkeit auf {value} gesetzt")
            return True
        except Exception as e:
            self.logger.log_error(f"Fehler beim Setzen der Helligkeit", exception=e)
            return False

    def set_contrast(self, value):
        """
        Setzt den Kontrast der Kamera.

        Args:
            value (float): Kontrastwert (0.0 bis 2.0, 1.0 = Standard)

        Returns:
            bool: True wenn erfolgreich
        """
        try:
            # Begrenze Wert auf gültigen Bereich
            value = max(0.0, min(2.0, value))
            self.contrast = value
            self._apply_camera_settings()
            self.logger.log_info(f"Kontrast auf {value} gesetzt")
            return True
        except Exception as e:
            self.logger.log_error(f"Fehler beim Setzen des Kontrasts", exception=e)
            return False

    def set_zoom(self, value):
        """
        Setzt den digitalen Zoom der Kamera.

        Args:
            value (float): Zoom-Level (1.0 = kein Zoom, 2.0 = 2x Zoom, max 4.0)

        Returns:
            bool: True wenn erfolgreich
        """
        try:
            # Begrenze Zoom auf sinnvollen Bereich
            value = max(1.0, min(4.0, value))
            self.zoom_level = value
            self._apply_camera_settings()
            self.logger.log_info(f"Zoom auf {value}x gesetzt")
            return True
        except Exception as e:
            self.logger.log_error(f"Fehler beim Setzen des Zooms", exception=e)
            return False

    def get_current_settings(self):
        """
        Gibt die aktuellen Kamera-Einstellungen zurück.

        Returns:
            dict: Dictionary mit allen Einstellungen
        """
        return {
            'resolution': self.resolution,
            'framerate': self.framerate,
            'brightness': self.brightness,
            'contrast': self.contrast,
            'saturation': self.saturation,
            'zoom': self.zoom_level,
            'is_recording': self.is_recording,
            'is_streaming': self.is_streaming
        }

    def capture_frame_mjpeg(self):
        """
        Erfasst ein einzelnes Frame für MJPEG-Streaming.
        Wird kontinuierlich von der Web-Server Streaming-Funktion aufgerufen.

        Returns:
            bytes: JPEG-kodiertes Bild oder None bei Fehler
        """
        try:
            with self.frame_lock:
                # Erfasse Frame als NumPy-Array
                frame = self.camera.capture_array()

                # Konvertiere NumPy-Array zu PIL-Image
                image = Image.fromarray(frame)

                # Kodiere als JPEG in Memory-Buffer
                buffer = io.BytesIO()
                image.save(buffer, format='JPEG', quality=85)

                # Hole JPEG-Daten
                jpeg_data = buffer.getvalue()

                return jpeg_data

        except Exception as e:
            self.logger.log_error("Fehler beim Erfassen des Frames", exception=e)
            return None

    def start_recording(self, output_path, gps_data=None):
        """
        Startet eine Video-Aufnahme im MP4-Format.

        Args:
            output_path (str): Vollständiger Pfad zur Ausgabe-Datei (z.B. /home/pi/.../recording.mp4)
            gps_data (dict): Optional - GPS-Daten für Metadaten

        Returns:
            tuple: (success: bool, message: str, recording_info: dict)
        """
        # Prüfe ob bereits eine Aufnahme läuft
        if self.is_recording:
            return (False, "Es läuft bereits eine Aufnahme", None)

        try:
            self.logger.log_info(f"Starte Video-Aufnahme: {output_path}")

            # Stelle sicher dass Ausgabe-Verzeichnis existiert
            output_dir = os.path.dirname(output_path)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            # Erstelle H.264-Encoder für MP4-Aufnahme
            self.encoder = H264Encoder(bitrate=10000000)  # 10 Mbps Bitrate

            # Erstelle File-Output
            output = FileOutput(output_path)

            # Starte Aufnahme
            self.camera.start_recording(self.encoder, output)

            # Speichere Aufnahme-Status
            self.is_recording = True
            self.recording_start_time = datetime.now()
            self.current_recording_path = output_path

            # Erstelle Aufnahme-Info
            recording_info = {
                'start_time': self.recording_start_time.isoformat(),
                'start_time_formatted': self.recording_start_time.strftime('%d.%m.%Y %H:%M:%S'),
                'path': output_path,
                'resolution': self.resolution,
                'framerate': self.framerate,
                'gps_data': gps_data
            }

            self.logger.log_info("Video-Aufnahme gestartet")
            return (True, "Aufnahme gestartet", recording_info)

        except Exception as e:
            self.is_recording = False
            self.logger.log_error("Fehler beim Starten der Aufnahme", exception=e)
            return (False, f"Fehler beim Starten: {str(e)}", None)

    def stop_recording(self):
        """
        Stoppt die laufende Video-Aufnahme.

        Returns:
            tuple: (success: bool, message: str, recording_stats: dict)
        """
        if not self.is_recording:
            return (False, "Keine Aufnahme läuft", None)

        try:
            self.logger.log_info("Stoppe Video-Aufnahme...")

            # Stoppe Aufnahme
            self.camera.stop_recording()

            # Berechne Aufnahme-Dauer
            recording_end_time = datetime.now()
            duration = recording_end_time - self.recording_start_time

            # Berechne Minuten und Sekunden
            total_seconds = int(duration.total_seconds())
            minutes = total_seconds // 60
            seconds = total_seconds % 60

            # Hole Datei-Größe
            file_size = 0
            if os.path.exists(self.current_recording_path):
                file_size = os.path.getsize(self.current_recording_path)
                file_size_mb = file_size / (1024 * 1024)
            else:
                file_size_mb = 0

            # Erstelle Statistiken
            recording_stats = {
                'start_time': self.recording_start_time.isoformat(),
                'end_time': recording_end_time.isoformat(),
                'duration_seconds': total_seconds,
                'duration_formatted': f"{minutes} Min {seconds} Sek",
                'file_path': self.current_recording_path,
                'file_size_bytes': file_size,
                'file_size_mb': round(file_size_mb, 2)
            }

            # Zurücksetzen der Aufnahme-Variablen
            self.is_recording = False
            self.recording_start_time = None
            recording_path = self.current_recording_path
            self.current_recording_path = None

            self.logger.log_info(f"Aufnahme gestoppt: {minutes}m {seconds}s, {recording_stats['file_size_mb']} MB")

            return (True, f"Aufnahme beendet: {minutes} Min {seconds} Sek", recording_stats)

        except Exception as e:
            self.is_recording = False
            self.logger.log_error("Fehler beim Stoppen der Aufnahme", exception=e)
            return (False, f"Fehler beim Stoppen: {str(e)}", None)

    def get_recording_duration(self):
        """
        Gibt die aktuelle Aufnahme-Dauer zurück (falls eine Aufnahme läuft).

        Returns:
            dict: {'duration_seconds': int, 'duration_formatted': str} oder None
        """
        if not self.is_recording or not self.recording_start_time:
            return None

        # Berechne vergangene Zeit seit Aufnahme-Start
        current_time = datetime.now()
        duration = current_time - self.recording_start_time
        total_seconds = int(duration.total_seconds())

        minutes = total_seconds // 60
        seconds = total_seconds % 60

        return {
            'duration_seconds': total_seconds,
            'duration_formatted': f"{minutes} Min {seconds} Sek",
            'start_time': self.recording_start_time.strftime('%d.%m.%Y %H:%M:%S')
        }

    def capture_snapshot(self, output_path):
        """
        Nimmt ein einzelnes Foto auf (Snapshot).

        Args:
            output_path (str): Pfad zur Ausgabe-Datei (z.B. snapshot.jpg)

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            self.logger.log_info(f"Erstelle Snapshot: {output_path}")

            # Stelle sicher dass Verzeichnis existiert
            output_dir = os.path.dirname(output_path)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            # Erfasse Bild
            self.camera.capture_file(output_path)

            # Hole Dateigröße
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                file_size_kb = file_size / 1024

                self.logger.log_info(f"Snapshot erstellt: {file_size_kb:.1f} KB")
                return (True, f"Snapshot erstellt: {file_size_kb:.1f} KB")
            else:
                return (False, "Snapshot-Datei wurde nicht erstellt")

        except Exception as e:
            self.logger.log_error("Fehler beim Erstellen des Snapshots", exception=e)
            return (False, f"Fehler: {str(e)}")

    def cleanup(self):
        """
        Beendet die Kamera und gibt Ressourcen frei.
        Sollte beim Herunterfahren des Systems aufgerufen werden.
        """
        try:
            self.logger.log_info("Beende Kamera...")

            # Stoppe laufende Aufnahme falls vorhanden
            if self.is_recording:
                self.stop_recording()

            # Stoppe und schließe Kamera
            if self.camera:
                self.camera.stop()
                self.camera.close()

            self.logger.log_info("Kamera erfolgreich beendet")

        except Exception as e:
            self.logger.log_error("Fehler beim Beenden der Kamera", exception=e)

    def __del__(self):
        """
        Destruktor - wird automatisch aufgerufen wenn Objekt gelöscht wird.
        Stellt sicher dass Kamera-Ressourcen freigegeben werden.
        """
        self.cleanup()


# ============================================================================
# Stream-Output-Klasse für MJPEG-Streaming
# ============================================================================
class StreamingOutput(io.BufferedIOBase):
    """
    Output-Klasse für kontinuierliches MJPEG-Streaming.
    Speichert das neueste Frame in einem Buffer für Web-Streaming.
    """

    def __init__(self):
        """Initialisiert den Streaming-Buffer."""
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        """
        Schreibt ein neues Frame in den Buffer.

        Args:
            buf (bytes): JPEG-Daten des aktuellen Frames
        """
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


# ============================================================================
# Beispiel-Verwendung (wird nur ausgeführt wenn Datei direkt gestartet wird)
# ============================================================================
if __name__ == "__main__":
    import json
    import sys

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from modules.logger import SystemLogger

    # Lade Konfiguration
    config_path = "/home/pi/camera_system/config/config.json"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
    else:
        # Test-Konfiguration
        config = {
            'camera': {
                'resolution': [1920, 1080],
                'framerate': 30,
                'brightness': 0.0,
                'contrast': 1.0,
                'saturation': 1.0,
                'resolution_4k': [3840, 2160],
                'framerate_4k': 60
            },
            'recording': {
                'save_path': '/tmp/recordings/'
            }
        }

    # Erstelle Logger
    logger = SystemLogger("/tmp/test_logs")

    # Erstelle Kamera-Controller
    print("\n=== Initialisiere Kamera ===")
    camera = CameraController(config, logger)

    # Zeige aktuelle Einstellungen
    print("\n=== Aktuelle Einstellungen ===")
    settings = camera.get_current_settings()
    print(f"Auflösung: {settings['resolution'][0]}x{settings['resolution'][1]}")
    print(f"Framerate: {settings['framerate']} fps")
    print(f"Helligkeit: {settings['brightness']}")
    print(f"Kontrast: {settings['contrast']}")
    print(f"Zoom: {settings['zoom']}x")

    # Teste Snapshot
    print("\n=== Teste Snapshot ===")
    success, msg = camera.capture_snapshot("/tmp/test_snapshot.jpg")
    print(f"Snapshot: {msg}")

    # Teste kurze Aufnahme (5 Sekunden)
    print("\n=== Teste Video-Aufnahme (5 Sekunden) ===")
    timestamp = datetime.now().strftime("%d_%m_%Y_%H.%M")
    recording_path = f"/tmp/recordings/test_recording_{timestamp}.mp4"

    success, msg, info = camera.start_recording(recording_path)
    print(f"Start: {msg}")

    if success:
        # Warte 5 Sekunden
        for i in range(5):
            time.sleep(1)
            duration = camera.get_recording_duration()
            if duration:
                print(f"  Aufnahme läuft: {duration['duration_formatted']}")

        # Stoppe Aufnahme
        success, msg, stats = camera.stop_recording()
        print(f"Stop: {msg}")
        if stats:
            print(f"  Dauer: {stats['duration_formatted']}")
            print(f"  Größe: {stats['file_size_mb']} MB")

    # Cleanup
    print("\n=== Beende Kamera ===")
    camera.cleanup()
    print("Test abgeschlossen!")
