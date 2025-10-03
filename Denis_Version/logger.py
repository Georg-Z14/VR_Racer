#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
Logging-System für Raspberry Pi 5 Kamera-Streaming-System
Datei: modules/logger.py
Version: 1.0
Datum: 30.09.2025

Funktionen:
- Fehlerprotokollierung in separate Datei (error.log)
- Zugriffsprotokollierung in separate Datei (access.log)
- Automatische Log-Rotation bei Überschreitung der Größe
- Farbige Konsolen-Ausgabe für bessere Lesbarkeit
============================================================================
Modul 7 - Logging-System
============================================================================

"""

import logging
import logging.handlers
import os
from datetime import datetime
import sys


class ColoredFormatter(logging.Formatter):
    """
    Formatter für farbige Konsolen-Ausgabe der Log-Nachrichten.
    Macht Fehler (rot), Warnungen (gelb) und Info (grün) leichter erkennbar.
    """

    # ANSI-Farb-Codes für Terminal-Ausgabe
    COLORS = {
        'DEBUG': '\033[36m',  # Cyan für Debug-Nachrichten
        'INFO': '\033[32m',  # Grün für Info-Nachrichten
        'WARNING': '\033[33m',  # Gelb für Warnungen
        'ERROR': '\033[31m',  # Rot für Fehler
        'CRITICAL': '\033[35m',  # Magenta für kritische Fehler
        'RESET': '\033[0m'  # Zurücksetzen auf Standard-Farbe
    }

    def format(self, record):
        """
        Formatiert eine Log-Nachricht mit Farbe basierend auf Level.

        Args:
            record: LogRecord-Objekt mit Log-Informationen

        Returns:
            str: Formatierte und eingefärbte Log-Nachricht
        """
        # Hole Farbe basierend auf Log-Level
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])

        # Formatiere Nachricht mit Standard-Formatter
        formatted_message = super().format(record)

        # Füge Farb-Codes hinzu
        return f"{color}{formatted_message}{self.COLORS['RESET']}"


class SystemLogger:
    """
    Haupt-Logger-Klasse für das gesamte Kamera-System.
    Erstellt separate Logger für Fehler und Zugriffe.
    """

    def __init__(self, log_dir, max_bytes=50 * 1024 * 1024, backup_count=5):
        """
        Initialisiert das Logging-System mit zwei separaten Log-Dateien.

        Args:
            log_dir (str): Verzeichnis für Log-Dateien (z.B. /home/pi/camera_system/logs/)
            max_bytes (int): Maximale Größe einer Log-Datei in Bytes (Standard: 50 MB)
            backup_count (int): Anzahl der zu behaltenden alten Log-Dateien (Standard: 5)
        """
        self.log_dir = log_dir
        self.max_bytes = max_bytes  # 50 MB = 50 * 1024 * 1024 Bytes
        self.backup_count = backup_count  # Behalte die letzten 5 Log-Dateien

        # Stelle sicher, dass Log-Verzeichnis existiert
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # Erstelle separate Logger für Fehler und Zugriffe
        self.error_logger = self._setup_error_logger()
        self.access_logger = self._setup_access_logger()

        # Erstelle auch System-Logger für allgemeine Nachrichten
        self.system_logger = self._setup_system_logger()

    def _setup_error_logger(self):
        """
        Erstellt Logger für Fehlerprotokollierung.
        Alle ERROR und CRITICAL Meldungen werden hier gespeichert.

        Returns:
            logging.Logger: Konfigurierter Error-Logger
        """
        # Erstelle Logger mit eindeutigem Namen
        logger = logging.getLogger('ErrorLogger')
        logger.setLevel(logging.ERROR)  # Nur ERROR und CRITICAL werden protokolliert

        # Verhindere doppelte Handler bei mehrfacher Initialisierung
        if logger.handlers:
            return logger

        # Erstelle Pfad zur Error-Log-Datei
        error_log_path = os.path.join(self.log_dir, 'error.log')

        # Erstelle Rotating File Handler (automatische Rotation bei max_bytes)
        file_handler = logging.handlers.RotatingFileHandler(
            error_log_path,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8'
        )

        # Definiere Format für Error-Logs (detailliert mit Dateiname und Zeile)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - '
            '[%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)

        # Füge Handler zum Logger hinzu
        logger.addHandler(file_handler)

        return logger

    def _setup_access_logger(self):
        """
        Erstellt Logger für Zugriffsprotokollierung.
        Protokolliert alle Zugriffe auf die Webseite (Login, Stream-Zugriffe, etc.)

        Returns:
            logging.Logger: Konfigurierter Access-Logger
        """
        # Erstelle Logger mit eindeutigem Namen
        logger = logging.getLogger('AccessLogger')
        logger.setLevel(logging.INFO)  # Alle INFO und höher werden protokolliert

        # Verhindere doppelte Handler
        if logger.handlers:
            return logger

        # Erstelle Pfad zur Access-Log-Datei
        access_log_path = os.path.join(self.log_dir, 'access.log')

        # Erstelle Rotating File Handler
        file_handler = logging.handlers.RotatingFileHandler(
            access_log_path,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8'
        )

        # Definiere Format für Access-Logs (kompakter, ähnlich Apache-Logs)
        formatter = logging.Formatter(
            '%(asctime)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)

        # Füge Handler zum Logger hinzu
        logger.addHandler(file_handler)

        return logger

    def _setup_system_logger(self):
        """
        Erstellt Logger für allgemeine System-Nachrichten.
        Dieser Logger schreibt in die Konsole UND in eine system.log Datei.

        Returns:
            logging.Logger: Konfigurierter System-Logger
        """
        # Erstelle Logger mit eindeutigem Namen
        logger = logging.getLogger('SystemLogger')
        logger.setLevel(logging.DEBUG)  # Alle Log-Level werden akzeptiert

        # Verhindere doppelte Handler
        if logger.handlers:
            return logger

        # 1. File Handler für system.log
        system_log_path = os.path.join(self.log_dir, 'system.log')
        file_handler = logging.handlers.RotatingFileHandler(
            system_log_path,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # 2. Console Handler für Bildschirm-Ausgabe (mit Farben)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)  # Nur INFO und höher auf Konsole
        console_formatter = ColoredFormatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        return logger

    def log_error(self, message, exception=None):
        """
        Protokolliert einen Fehler in die error.log Datei.

        Args:
            message (str): Fehlerbeschreibung
            exception (Exception): Optional - Exception-Objekt für Details
        """
        if exception:
            # Füge Exception-Details hinzu
            self.error_logger.error(f"{message} - Exception: {str(exception)}", exc_info=True)
        else:
            self.error_logger.error(message)

    def log_access(self, username, action, ip_address=None, details=None):
        """
        Protokolliert einen Zugriff auf das System in access.log.

        Args:
            username (str): Benutzername des zugreifenden Users
            action (str): Durchgeführte Aktion (z.B. "Login", "Stream-Start")
            ip_address (str): Optional - IP-Adresse des Clients
            details (str): Optional - Zusätzliche Details
        """
        # Erstelle formatierte Access-Log-Nachricht
        log_message = f"User: {username} | Action: {action}"

        if ip_address:
            log_message += f" | IP: {ip_address}"

        if details:
            log_message += f" | Details: {details}"

        self.access_logger.info(log_message)

    def log_info(self, message):
        """
        Protokolliert eine Info-Nachricht (System-Log und Konsole).

        Args:
            message (str): Info-Nachricht
        """
        self.system_logger.info(message)

    def log_warning(self, message):
        """
        Protokolliert eine Warnung (System-Log und Konsole).

        Args:
            message (str): Warn-Nachricht
        """
        self.system_logger.warning(message)

    def log_debug(self, message):
        """
        Protokolliert eine Debug-Nachricht (nur System-Log, nicht Konsole).

        Args:
            message (str): Debug-Nachricht
        """
        self.system_logger.debug(message)

    def log_critical(self, message, exception=None):
        """
        Protokolliert einen kritischen Fehler.
        Wird in error.log UND auf der Konsole angezeigt.

        Args:
            message (str): Kritische Fehlermeldung
            exception (Exception): Optional - Exception-Objekt
        """
        if exception:
            self.error_logger.critical(f"{message} - Exception: {str(exception)}", exc_info=True)
            self.system_logger.critical(f"{message} - Exception: {str(exception)}")
        else:
            self.error_logger.critical(message)
            self.system_logger.critical(message)

    def get_log_stats(self):
        """
        Holt Statistiken über die Log-Dateien (Größe, Anzahl Zeilen).

        Returns:
            dict: Statistiken über alle Log-Dateien
        """
        stats = {}

        # Liste aller Log-Dateien
        log_files = ['error.log', 'access.log', 'system.log']

        for log_file in log_files:
            log_path = os.path.join(self.log_dir, log_file)

            if os.path.exists(log_path):
                # Hole Dateigröße in MB
                size_bytes = os.path.getsize(log_path)
                size_mb = size_bytes / (1024 * 1024)

                # Zähle Anzahl Zeilen
                with open(log_path, 'r', encoding='utf-8') as f:
                    line_count = sum(1 for _ in f)

                stats[log_file] = {
                    'size_mb': round(size_mb, 2),
                    'size_bytes': size_bytes,
                    'line_count': line_count,
                    'path': log_path
                }
            else:
                stats[log_file] = {
                    'size_mb': 0,
                    'size_bytes': 0,
                    'line_count': 0,
                    'path': log_path,
                    'exists': False
                }

        return stats

    def clear_logs(self):
        """
        Löscht alle Log-Dateien (nur für Admin-Funktion).
        VORSICHT: Diese Aktion kann nicht rückgängig gemacht werden!

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            log_files = ['error.log', 'access.log', 'system.log']
            deleted_count = 0

            for log_file in log_files:
                log_path = os.path.join(self.log_dir, log_file)

                if os.path.exists(log_path):
                    os.remove(log_path)
                    deleted_count += 1

                # Lösche auch rotierte Log-Dateien (.1, .2, etc.)
                for i in range(1, self.backup_count + 1):
                    rotated_path = f"{log_path}.{i}"
                    if os.path.exists(rotated_path):
                        os.remove(rotated_path)
                        deleted_count += 1

            self.log_info(f"Log-Dateien gelöscht: {deleted_count} Dateien")
            return (True, f"{deleted_count} Log-Dateien wurden gelöscht")

        except Exception as e:
            self.log_error("Fehler beim Löschen der Log-Dateien", e)
            return (False, f"Fehler beim Löschen: {str(e)}")


# ============================================================================
# Beispiel-Verwendung (wird nur ausgeführt wenn Datei direkt gestartet wird)
# ============================================================================
if __name__ == "__main__":
    # Erstelle Logger-Instanz
    logger = SystemLogger("/tmp/test_logs")

    # Teste verschiedene Log-Level
    print("\n=== Test: Verschiedene Log-Level ===")
    logger.log_info("System gestartet")
    logger.log_debug("Debug-Information: Variable X = 42")
    logger.log_warning("Warnung: Speicher wird knapp (20% frei)")
    logger.log_error("Fehler beim Lesen der Konfigurationsdatei")
    logger.log_critical("KRITISCH: Kamera nicht gefunden!")

    # Teste Access-Logging
    print("\n=== Test: Access-Logging ===")
    logger.log_access("Admin_G", "Login", ip_address="192.168.1.100")
    logger.log_access("TestUser", "Stream-Start", ip_address="192.168.1.105", details="Full HD Stream")
    logger.log_access("Admin_D", "Aufnahme-Start", ip_address="192.168.1.100", details="4K @ 60fps")

    # Teste Fehler mit Exception
    print("\n=== Test: Fehler mit Exception ===")
    try:
        # Simuliere einen Fehler
        result = 10 / 0
    except Exception as e:
        logger.log_error("Division durch Null", exception=e)

    # Zeige Log-Statistiken
    print("\n=== Log-Statistiken ===")
    stats = logger.get_log_stats()
    for log_name, log_stats in stats.items():
        if log_stats.get('exists', True):
            print(f"{log_name}:")
            print(f"  Größe: {log_stats['size_mb']} MB")
            print(f"  Zeilen: {log_stats['line_count']}")
        else:
            print(f"{log_name}: Nicht vorhanden")
