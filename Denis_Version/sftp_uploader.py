#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
SFTP-Upload-Modul für Raspberry Pi 5 Kamera-Streaming-System
Datei: modules/sftp_uploader.py
Version: 1.0
Datum: 30.09.2025

Funktionen:
- Automatischer Upload von Aufnahmen auf eigenen SFTP-Server
- Verbindungsmanagement mit Fehlerbehandlung
- Retry-Logik bei Verbindungsproblemen
- Upload-Fortschrittsanzeige
- Automatische Löschung lokaler Dateien nach 7 Tagen
- Sichere SSH-Verbindung (Port 22)
============================================================================
Modul 6 - SFTP -Upload 
============================================================================

"""

import os
import time
from datetime import datetime, timedelta
import logging
import paramiko
from stat import S_ISDIR

# pysftp ist eine High-Level SFTP-Bibliothek basierend auf paramiko
try:
    import pysftp

    PYSFTP_AVAILABLE = True
except ImportError:
    PYSFTP_AVAILABLE = False
    print("WARNUNG: pysftp-Bibliothek nicht installiert. SFTP-Upload deaktiviert.")
    print("Installation: pip install pysftp")


class SFTPUploader:
    """
    Klasse für automatischen Upload von Video-Aufnahmen auf SFTP-Server.
    Verwaltet Verbindung, Upload und lokale Datei-Bereinigung.
    """

    def __init__(self, config, logger):
        """
        Initialisiert den SFTP-Uploader.

        Args:
            config (dict): SFTP-Konfiguration aus config.json
            logger (SystemLogger): Logger-Instanz für Protokollierung
        """
        self.config = config
        self.logger = logger

        # SFTP-Konfiguration aus config.json
        self.sftp_enabled = config['sftp'].get('enabled', False)
        self.host = config['sftp'].get('host', 'SERVER_IP_ODER_HOSTNAME')
        self.port = config['sftp'].get('port', 22)
        self.username = config['sftp'].get('username', 'upload_user')
        self.password = config['sftp'].get('password', 'PLATZHALTER_PASSWORT')
        self.remote_path = config['sftp'].get('remote_path', '/uploads/recordings/')
        self.auto_upload = config['sftp'].get('auto_upload', True)
        self.delete_after_upload = config['sftp'].get('delete_after_upload', False)
        self.timeout = config['sftp'].get('timeout', 30)

        # Automatische Bereinigung nach 7 Tagen
        self.auto_cleanup_days = config['storage'].get('auto_cleanup_days', 7)

        # SFTP-Verbindung (wird bei Bedarf erstellt)
        self.sftp_connection = None
        self.is_connected = False

        # Prüfe ob SFTP konfiguriert wurde
        if self.host == 'SERVER_IP_ODER_HOSTNAME':
            self.logger.log_warning(
                "SFTP-Server nicht konfiguriert! "
                "Bitte in config.json anpassen."
            )

    def connect(self):
        """
        Stellt Verbindung zum SFTP-Server her.

        Returns:
            tuple: (success: bool, message: str)
        """
        if not PYSFTP_AVAILABLE:
            return (False, "pysftp-Bibliothek nicht installiert")

        if not self.sftp_enabled:
            return (False, "SFTP ist deaktiviert (config: sftp.enabled = false)")

        try:
            self.logger.log_info(f"Verbinde mit SFTP-Server: {self.host}:{self.port}")

            # Erstelle SFTP-Verbindungsoptionen
            cnopts = pysftp.CnOpts()
            # Deaktiviere Host-Key-Überprüfung (für selbst-signierte Zertifikate)
            # WARNUNG: In Production sollte Host-Key überprüft werden!
            cnopts.hostkeys = None

            # Stelle Verbindung her
            self.sftp_connection = pysftp.Connection(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                cnopts=cnopts,
                timeout=self.timeout
            )

            self.is_connected = True
            self.logger.log_info(f"SFTP-Verbindung erfolgreich hergestellt zu {self.host}")

            # Prüfe ob Remote-Verzeichnis existiert
            if not self.sftp_connection.exists(self.remote_path):
                self.logger.log_info(f"Erstelle Remote-Verzeichnis: {self.remote_path}")
                self._create_remote_directory(self.remote_path)

            return (True, "SFTP-Verbindung erfolgreich")

        except paramiko.AuthenticationException as e:
            error_msg = "SFTP-Authentifizierung fehlgeschlagen - Falscher Benutzername/Passwort"
            self.logger.log_error(error_msg, exception=e)
            self.is_connected = False
            return (False, error_msg)

        except paramiko.SSHException as e:
            error_msg = f"SSH-Fehler beim Verbinden mit SFTP-Server: {str(e)}"
            self.logger.log_error(error_msg, exception=e)
            self.is_connected = False
            return (False, error_msg)

        except Exception as e:
            error_msg = f"Fehler beim Verbinden mit SFTP-Server: {str(e)}"
            self.logger.log_error(error_msg, exception=e)
            self.is_connected = False
            return (False, error_msg)

    def _create_remote_directory(self, path):
        """
        Erstellt ein Remote-Verzeichnis (und alle übergeordneten Verzeichnisse).

        Args:
            path (str): Pfad des zu erstellenden Verzeichnisses

        Returns:
            bool: True wenn erfolgreich
        """
        try:
            # Teile Pfad in einzelne Verzeichnisse
            parts = path.strip('/').split('/')
            current_path = ''

            for part in parts:
                current_path += '/' + part

                # Prüfe ob Verzeichnis existiert
                if not self.sftp_connection.exists(current_path):
                    # Erstelle Verzeichnis
                    self.sftp_connection.mkdir(current_path)
                    self.logger.log_info(f"Remote-Verzeichnis erstellt: {current_path}")

            return True

        except Exception as e:
            self.logger.log_error(f"Fehler beim Erstellen des Remote-Verzeichnisses: {path}", exception=e)
            return False

    def disconnect(self):
        """
        Trennt die SFTP-Verbindung.
        """
        try:
            if self.sftp_connection and self.is_connected:
                self.sftp_connection.close()
                self.is_connected = False
                self.logger.log_info("SFTP-Verbindung getrennt")

        except Exception as e:
            self.logger.log_error("Fehler beim Trennen der SFTP-Verbindung", exception=e)

    def upload_file(self, local_path, remote_filename=None, retry_count=3):
        """
        Lädt eine Datei auf den SFTP-Server hoch.

        Args:
            local_path (str): Pfad zur lokalen Datei
            remote_filename (str): Optional - Name auf dem Server (Standard: wie lokal)
            retry_count (int): Anzahl Wiederholungsversuche bei Fehler

        Returns:
            tuple: (success: bool, message: str, upload_info: dict)
        """
        # Prüfe ob Datei existiert
        if not os.path.exists(local_path):
            return (False, f"Lokale Datei nicht gefunden: {local_path}", None)

        # Verwende lokalen Dateinamen wenn kein Remote-Name angegeben
        if not remote_filename:
            remote_filename = os.path.basename(local_path)

        # Vollständiger Remote-Pfad
        remote_path = os.path.join(self.remote_path, remote_filename).replace('\\', '/')

        # Hole Dateigröße für Fortschrittsanzeige
        file_size = os.path.getsize(local_path)
        file_size_mb = file_size / (1024 ** 2)

        self.logger.log_info(
            f"Starte Upload: {os.path.basename(local_path)} "
            f"({file_size_mb:.2f} MB) -> {remote_path}"
        )

        # Versuche Upload mit Retry-Logik
        last_error = None

        for attempt in range(retry_count):
            try:
                # Stelle Verbindung her falls nicht verbunden
                if not self.is_connected:
                    success, msg = self.connect()
                    if not success:
                        return (False, msg, None)

                # Upload-Start-Zeit für Geschwindigkeitsberechnung
                start_time = time.time()

                # Führe Upload durch mit Fortschritts-Callback
                self.sftp_connection.put(
                    local_path,
                    remote_path,
                    callback=lambda sent, total: self._upload_progress(sent, total, file_size_mb)
                )

                # Berechne Upload-Dauer und Geschwindigkeit
                upload_duration = time.time() - start_time
                upload_speed_mbps = (file_size_mb / upload_duration) if upload_duration > 0 else 0

                # Erstelle Upload-Informationen
                upload_info = {
                    'local_path': local_path,
                    'remote_path': remote_path,
                    'file_size_mb': round(file_size_mb, 2),
                    'upload_duration_seconds': round(upload_duration, 2),
                    'upload_speed_mbps': round(upload_speed_mbps, 2),
                    'timestamp': datetime.now().isoformat()
                }

                self.logger.log_info(
                    f"Upload erfolgreich: {remote_filename} "
                    f"({file_size_mb:.2f} MB in {upload_duration:.1f}s, "
                    f"{upload_speed_mbps:.2f} MB/s)"
                )

                # Lösche lokale Datei falls konfiguriert (NICHT für 7-Tage-Regel)
                if self.delete_after_upload:
                    try:
                        os.remove(local_path)
                        self.logger.log_info(f"Lokale Datei gelöscht nach Upload: {local_path}")
                    except Exception as e:
                        self.logger.log_warning(f"Fehler beim Löschen der lokalen Datei: {e}")

                return (True, "Upload erfolgreich", upload_info)

            except IOError as e:
                last_error = f"IO-Fehler beim Upload: {str(e)}"
                self.logger.log_warning(f"Upload-Versuch {attempt + 1}/{retry_count} fehlgeschlagen: {last_error}")

                # Trenne und verbinde neu für nächsten Versuch
                self.disconnect()

                if attempt < retry_count - 1:
                    time.sleep(5)  # Warte 5 Sekunden vor erneutem Versuch

            except Exception as e:
                last_error = str(e)
                self.logger.log_error(f"Unerwarteter Fehler beim Upload", exception=e)

                self.disconnect()

                if attempt < retry_count - 1:
                    time.sleep(5)

        # Alle Versuche fehlgeschlagen
        return (False, f"Upload nach {retry_count} Versuchen fehlgeschlagen: {last_error}", None)

    def _upload_progress(self, sent, total, file_size_mb):
        """
        Callback-Funktion für Upload-Fortschritt.

        Args:
            sent (int): Bereits gesendete Bytes
            total (int): Gesamt-Bytes
            file_size_mb (float): Dateigröße in MB
        """
        # Berechne Prozent
        if total > 0:
            percent = (sent / total) * 100

            # Logge nur bei jedem 10%-Schritt um Logs nicht zu überfüllen
            if int(percent) % 10 == 0 and int(percent) > 0:
                self.logger.log_debug(
                    f"Upload-Fortschritt: {percent:.0f}% "
                    f"({sent / (1024 ** 2):.1f} / {file_size_mb:.1f} MB)"
                )

    def upload_recording(self, recording_path):
        """
        Lädt eine Video-Aufnahme auf den Server hoch (mit Auto-Cleanup).

        Args:
            recording_path (str): Pfad zur Video-Aufnahme

        Returns:
            tuple: (success: bool, message: str, upload_info: dict)
        """
        if not self.sftp_enabled:
            return (False, "SFTP ist deaktiviert", None)

        # Führe Upload durch
        success, message, upload_info = self.upload_file(recording_path)

        # Wenn Upload erfolgreich: Markiere Datei für späteren Cleanup (nach 7 Tagen)
        if success and not self.delete_after_upload:
            self.logger.log_info(
                f"Datei wird lokal behalten für {self.auto_cleanup_days} Tage: "
                f"{os.path.basename(recording_path)}"
            )

        return (success, message, upload_info)

    def cleanup_old_local_files(self, recordings_path):
        """
        Löscht lokale Aufnahmen die älter als X Tage sind (Standard: 7 Tage).
        Wird automatisch aufgerufen wenn SFTP aktiviert ist.

        Args:
            recordings_path (str): Pfad zum Aufnahmen-Verzeichnis

        Returns:
            tuple: (deleted_count: int, freed_space_mb: float)
        """
        try:
            deleted_count = 0
            freed_space = 0
            current_time = datetime.now()
            cutoff_date = current_time - timedelta(days=self.auto_cleanup_days)

            self.logger.log_info(
                f"Starte Cleanup von Dateien älter als {self.auto_cleanup_days} Tage "
                f"(vor {cutoff_date.strftime('%d.%m.%Y')})"
            )

            # Durchsuche Aufnahmen-Verzeichnis
            if not os.path.exists(recordings_path):
                return (0, 0.0)

            for filename in os.listdir(recordings_path):
                file_path = os.path.join(recordings_path, filename)

                # Prüfe nur Dateien (keine Verzeichnisse)
                if not os.path.isfile(file_path):
                    continue

                # Hole Datei-Erstellungszeit
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))

                # Lösche wenn älter als cutoff_date
                if file_time < cutoff_date:
                    file_size = os.path.getsize(file_path)

                    try:
                        os.remove(file_path)
                        deleted_count += 1
                        freed_space += file_size

                        age_days = (current_time - file_time).days
                        self.logger.log_info(
                            f"Alte Datei gelöscht: {filename} "
                            f"(Alter: {age_days} Tage)"
                        )

                    except Exception as e:
                        self.logger.log_error(f"Fehler beim Löschen von {filename}", exception=e)

            freed_space_mb = freed_space / (1024 ** 2)

            if deleted_count > 0:
                self.logger.log_info(
                    f"Cleanup abgeschlossen: {deleted_count} Dateien gelöscht, "
                    f"{freed_space_mb:.2f} MB freigegeben"
                )
            else:
                self.logger.log_info("Cleanup abgeschlossen: Keine alten Dateien gefunden")

            return (deleted_count, round(freed_space_mb, 2))

        except Exception as e:
            self.logger.log_error("Fehler beim Cleanup alter Dateien", exception=e)
            return (0, 0.0)

    def list_remote_files(self):
        """
        Listet alle Dateien im Remote-Verzeichnis auf.

        Returns:
            list: Liste von Dateinamen oder None bei Fehler
        """
        if not self.is_connected:
            success, msg = self.connect()
            if not success:
                return None

        try:
            # Liste alle Dateien im Remote-Verzeichnis
            files = []

            if self.sftp_connection.exists(self.remote_path):
                for entry in self.sftp_connection.listdir_attr(self.remote_path):
                    # Nur Dateien (keine Verzeichnisse)
                    if not S_ISDIR(entry.st_mode):
                        files.append({
                            'filename': entry.filename,
                            'size_bytes': entry.st_size,
                            'size_mb': round(entry.st_size / (1024 ** 2), 2),
                            'modified': datetime.fromtimestamp(entry.st_mtime).isoformat()
                        })

            return files

        except Exception as e:
            self.logger.log_error("Fehler beim Auflisten der Remote-Dateien", exception=e)
            return None

    def get_remote_storage_usage(self):
        """
        Berechnet den Speicherverbrauch auf dem Remote-Server.

        Returns:
            dict: Speicher-Informationen oder None bei Fehler
        """
        files = self.list_remote_files()

        if files is None:
            return None

        total_size = sum(f['size_bytes'] for f in files)
        total_size_mb = total_size / (1024 ** 2)
        total_size_gb = total_size / (1024 ** 3)

        return {
            'file_count': len(files),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size_mb, 2),
            'total_size_gb': round(total_size_gb, 2),
            'files': files
        }

    def test_connection(self):
        """
        Testet die SFTP-Verbindung ohne Daten zu übertragen.

        Returns:
            tuple: (success: bool, message: str)
        """
        success, message = self.connect()

        if success:
            self.disconnect()

        return (success, message)

    def get_sftp_status(self):
        """
        Gibt den aktuellen Status der SFTP-Konfiguration zurück.

        Returns:
            dict: Status-Informationen
        """
        is_configured = (
                self.host != 'SERVER_IP_ODER_HOSTNAME' and
                self.password != 'PLATZHALTER_PASSWORT'
        )

        return {
            'enabled': self.sftp_enabled,
            'configured': is_configured,
            'connected': self.is_connected,
            'host': self.host if is_configured else "Nicht konfiguriert",
            'port': self.port,
            'username': self.username if is_configured else "Nicht konfiguriert",
            'remote_path': self.remote_path,
            'auto_upload': self.auto_upload,
            'auto_cleanup_days': self.auto_cleanup_days,
            'delete_after_upload': self.delete_after_upload
        }

    def __del__(self):
        """
        Destruktor - stellt sicher dass SFTP-Verbindung getrennt wird.
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
        'sftp': {
            'enabled': False,  # Auf True setzen für echten Test
            'host': 'SERVER_IP_ODER_HOSTNAME',
            'port': 22,
            'username': 'upload_user',
            'password': 'PLATZHALTER_PASSWORT',
            'remote_path': '/uploads/recordings/',
            'auto_upload': True,
            'delete_after_upload': False,
            'timeout': 30
        },
        'storage': {
            'auto_cleanup_days': 7
        }
    }

    # Erstelle Logger
    logger = SystemLogger("/tmp/test_logs")

    # Erstelle SFTP-Uploader
    print("\n=== SFTP-Uploader Test ===")
    uploader = SFTPUploader(config, logger)

    # Zeige SFTP-Status
    print("\n=== SFTP-Status ===")
    status = uploader.get_sftp_status()
    print(f"Aktiviert: {status['enabled']}")
    print(f"Konfiguriert: {status['configured']}")
    print(f"Verbunden: {status['connected']}")
    print(f"Host: {status['host']}:{status['port']}")
    print(f"Benutzername: {status['username']}")
    print(f"Remote-Pfad: {status['remote_path']}")
    print(f"Auto-Upload: {status['auto_upload']}")
    print(f"Auto-Cleanup: {status['auto_cleanup_days']} Tage")
    print(f"Löschen nach Upload: {status['delete_after_upload']}")

    # Teste Verbindung (funktioniert nur mit echten Server-Daten)
    print("\n=== SFTP-Verbindungstest ===")
    if status['configured'] and status['enabled']:
        success, msg = uploader.test_connection()
        print(f"Ergebnis: {msg}")

        if success:
            # Liste Remote-Dateien
            print("\n=== Remote-Dateien ===")
            files = uploader.list_remote_files()
            if files:
                for file in files:
                    print(f"- {file['filename']} ({file['size_mb']} MB)")
            else:
                print("Keine Dateien gefunden oder Fehler beim Auflisten")

            # Zeige Speichernutzung
            print("\n=== Remote-Speicher ===")
            storage = uploader.get_remote_storage_usage()
            if storage:
                print(f"Dateien: {storage['file_count']}")
                print(f"Größe: {storage['total_size_gb']} GB")
    else:
        print("Überspringe Test - SFTP nicht konfiguriert oder deaktiviert")
        print("\nUm SFTP zu aktivieren:")
        print("1. In config.json sftp.enabled auf true setzen")
        print("2. Server-Zugangsdaten eintragen:")
        print("   - host: IP oder Hostname des Servers")
        print("   - username: SFTP-Benutzername")
        print("   - password: SFTP-Passwort")
        print("3. remote_path anpassen (Ziel-Verzeichnis auf Server)")

    # Teste Cleanup (mit Test-Verzeichnis)
    print("\n=== Teste Auto-Cleanup ===")
    test_recordings_path = "/tmp/test_recordings"
    if not os.path.exists(test_recordings_path):
        os.makedirs(test_recordings_path)
        print(f"Test-Verzeichnis erstellt: {test_recordings_path}")

    deleted, freed = uploader.cleanup_old_local_files(test_recordings_path)
    print(f"Gelöscht: {deleted} Dateien, {freed} MB freigegeben")

    print("\n=== Test abgeschlossen ===")
