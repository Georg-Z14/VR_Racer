#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
Email-Versand-Modul für Raspberry Pi 5 Kamera-Streaming-System
Datei: modules/email_sender.py
Version: 1.0
Datum: 30.09.2025

Funktionen:
- Email-Versand über Outlook SMTP (smtp-mail.outlook.com)
- Aufnahmen als Anhang versenden
- GPS-Karten-Screenshot anhängen
- Fahrtzeit und Datum in Email
- Dankestext für Normal-User
- Fehlerbehandlung und Retry-Logik
============================================================================
Modul 5 - Email-Versand
============================================================================

"""

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import time
import logging


class EmailSender:
    """
    Klasse für den Versand von Emails mit Video-Aufnahmen und GPS-Daten.
    Verwendet Outlook SMTP-Server.
    """

    def __init__(self, config, logger, utils):
        """
        Initialisiert den Email-Sender.

        Args:
            config (dict): Email-Konfiguration aus config.json
            logger (SystemLogger): Logger-Instanz für Protokollierung
            utils (SystemUtils): Utils-Instanz für Hilfsfunktionen
        """
        self.config = config
        self.logger = logger
        self.utils = utils

        # SMTP-Konfiguration aus config.json
        self.smtp_server = config['email']['smtp_server']  # smtp-mail.outlook.com
        self.smtp_port = config['email']['smtp_port']  # 587 für TLS
        self.sender_email = config['email']['sender_email']
        self.sender_password = config['email']['sender_password']
        self.use_tls = config['email'].get('use_tls', True)

        # Dankestext aus Konfiguration
        self.thank_you_message = config['email'].get(
            'thank_you_message',
            'Vielen Dank für die Teilnahme an unserem Kamera-System!'
        )

        # Prüfe ob Zugangsdaten konfiguriert wurden
        if self.sender_email == "PLATZHALTER@outlook.com":
            self.logger.log_warning(
                "Email-Zugangsdaten nicht konfiguriert! "
                "Bitte in config.json anpassen."
            )

    def send_recording_email(self, recipient_email, username, recording_path,
                             recording_stats, gps_map_path=None):
        """
        Sendet eine Email mit Video-Aufnahme an einen Benutzer.
        Enthält Dankestext, Aufnahme-Details und optional GPS-Karte.

        Args:
            recipient_email (str): Email-Adresse des Empfängers
            username (str): Benutzername des Empfängers
            recording_path (str): Pfad zur Video-Datei
            recording_stats (dict): Statistiken der Aufnahme (Dauer, Datum, etc.)
            gps_map_path (str): Optional - Pfad zum GPS-Karten-Screenshot

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            self.logger.log_info(f"Bereite Email vor für: {recipient_email}")

            # Prüfe ob Video-Datei existiert
            if not os.path.exists(recording_path):
                return (False, f"Video-Datei nicht gefunden: {recording_path}")

            # Prüfe Dateigröße (Warnung bei >25 MB - typisches Email-Limit)
            file_size_mb = os.path.getsize(recording_path) / (1024 ** 2)
            if file_size_mb > 25:
                self.logger.log_warning(
                    f"Video sehr groß ({file_size_mb:.1f} MB) - "
                    "Email könnte abgelehnt werden"
                )

            # Erstelle Email-Nachricht
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = recipient_email
            msg['Subject'] = f"Ihre Video-Aufnahme vom {recording_stats.get('start_time_formatted', 'heute')}"

            # Erstelle Email-Text mit allen Informationen
            email_body = self._create_email_body(username, recording_stats)

            # Füge Text als HTML hinzu (für bessere Formatierung)
            msg.attach(MIMEText(email_body, 'html', 'utf-8'))

            # Füge Video-Aufnahme als Anhang hinzu
            self.logger.log_info("Füge Video-Datei hinzu...")
            success = self._attach_file(msg, recording_path, 'video/mp4')
            if not success:
                return (False, "Fehler beim Anhängen der Video-Datei")

            # Füge GPS-Karten-Screenshot hinzu (falls vorhanden)
            if gps_map_path and os.path.exists(gps_map_path):
                self.logger.log_info("Füge GPS-Karte hinzu...")
                self._attach_file(msg, gps_map_path, 'image/png')

            # Sende Email
            self.logger.log_info(f"Sende Email an {recipient_email}...")
            success, message = self._send_email(msg)

            if success:
                self.logger.log_info(f"Email erfolgreich gesendet an {recipient_email}")
                return (True, f"Email erfolgreich an {recipient_email} gesendet")
            else:
                return (False, f"Fehler beim Senden: {message}")

        except Exception as e:
            self.logger.log_error(f"Fehler beim Erstellen der Email für {recipient_email}", exception=e)
            return (False, f"Fehler: {str(e)}")

    def _create_email_body(self, username, recording_stats):
        """
        Erstellt den HTML-formatierten Email-Text mit allen Informationen.

        Args:
            username (str): Benutzername des Empfängers
            recording_stats (dict): Aufnahme-Statistiken

        Returns:
            str: HTML-formatierter Email-Text
        """
        # Hole Aufnahme-Details
        start_time = recording_stats.get('start_time_formatted', 'N/A')
        duration = recording_stats.get('duration_formatted', 'N/A')
        file_size = recording_stats.get('file_size_mb', 0)

        # GPS-Daten falls vorhanden
        gps_data = recording_stats.get('gps_data')
        gps_info = ""
        if gps_data:
            gps_info = f"""
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;"><strong>GPS-Position (Start):</strong></td>
                <td style="padding: 8px; border: 1px solid #ddd;">
                    Lat: {gps_data.get('latitude', 'N/A'):.4f}, 
                    Lon: {gps_data.get('longitude', 'N/A'):.4f}
                </td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;"><strong>Geschwindigkeit:</strong></td>
                <td style="padding: 8px; border: 1px solid #ddd;">{gps_data.get('speed', 0):.1f} km/h</td>
            </tr>
            """

        # Erstelle HTML-Email
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .header {{
                    background-color: #4CAF50;
                    color: white;
                    padding: 20px;
                    text-align: center;
                }}
                .content {{
                    padding: 20px;
                    background-color: #f9f9f9;
                }}
                .info-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                    background-color: white;
                }}
                .footer {{
                    padding: 20px;
                    text-align: center;
                    background-color: #333;
                    color: white;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🎥 Ihre Video-Aufnahme</h1>
            </div>

            <div class="content">
                <p>Hallo <strong>{username}</strong>,</p>

                <p>{self.thank_you_message}</p>

                <p>Anbei finden Sie Ihre angeforderte Video-Aufnahme mit folgenden Details:</p>

                <table class="info-table">
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd; width: 40%;"><strong>Aufnahme-Datum:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{start_time}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Fahrtzeit (Aufnahmedauer):</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{duration}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Dateigröße:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{file_size:.2f} MB</td>
                    </tr>
                    {gps_info}
                </table>

                <p><strong>Anhänge:</strong></p>
                <ul>
                    <li>📹 Video-Aufnahme (MP4-Format)</li>
                    {"<li>🗺️ GPS-Route (Karten-Screenshot)</li>" if gps_info else ""}
                </ul>

                <p style="margin-top: 30px; padding: 15px; background-color: #e7f3fe; border-left: 4px solid #2196F3;">
                    <strong>Hinweis:</strong> Diese Aufnahme wurde automatisch erstellt und versendet. 
                    Bei Fragen wenden Sie sich bitte an den Administrator.
                </p>
            </div>

            <div class="footer">
                <p>Raspberry Pi 5 Kamera-Streaming-System</p>
                <p>Generiert am {self.utils.get_current_datetime_formatted()}</p>
            </div>
        </body>
        </html>
        """

        return html_body

    def _attach_file(self, msg, file_path, mime_type):
        """
        Fügt eine Datei als Anhang zur Email hinzu.

        Args:
            msg (MIMEMultipart): Email-Nachricht
            file_path (str): Pfad zur anzuhängenden Datei
            mime_type (str): MIME-Type der Datei (z.B. 'video/mp4', 'image/png')

        Returns:
            bool: True wenn erfolgreich, False bei Fehler
        """
        try:
            # Hole Dateinamen
            filename = os.path.basename(file_path)

            # Öffne Datei im Binär-Modus
            with open(file_path, 'rb') as f:
                # Erstelle MIMEBase-Objekt
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())

            # Kodiere Datei in Base64 für Email-Transport
            encoders.encode_base64(part)

            # Füge Header hinzu
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {filename}'
            )

            # Füge zur Email hinzu
            msg.attach(part)

            return True

        except Exception as e:
            self.logger.log_error(f"Fehler beim Anhängen der Datei: {file_path}", exception=e)
            return False

    def _send_email(self, msg, retry_count=3, retry_delay=5):
        """
        Sendet die Email über SMTP mit Retry-Logik.

        Args:
            msg (MIMEMultipart): Zu sendende Email-Nachricht
            retry_count (int): Anzahl der Wiederholungsversuche bei Fehler
            retry_delay (int): Wartezeit zwischen Versuchen in Sekunden

        Returns:
            tuple: (success: bool, message: str)
        """
        last_error = None

        # Versuche Email zu senden (mit mehreren Versuchen)
        for attempt in range(retry_count):
            try:
                self.logger.log_info(f"Email-Versand Versuch {attempt + 1}/{retry_count}")

                # Erstelle SMTP-Verbindung
                server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)

                # Aktiviere Debug-Ausgabe (nur für Entwicklung)
                # server.set_debuglevel(1)

                # Starte TLS-Verschlüsselung wenn aktiviert
                if self.use_tls:
                    server.ehlo()  # Identifiziere Client
                    server.starttls()  # Starte TLS
                    server.ehlo()  # Identifiziere erneut nach TLS

                # Login mit Outlook-Zugangsdaten
                self.logger.log_info("Authentifiziere mit Outlook...")
                server.login(self.sender_email, self.sender_password)

                # Sende Email
                self.logger.log_info("Sende Email-Nachricht...")
                server.send_message(msg)

                # Schließe Verbindung
                server.quit()

                return (True, "Email erfolgreich gesendet")

            except smtplib.SMTPAuthenticationError as e:
                # Authentifizierungs-Fehler (falsches Passwort)
                error_msg = "SMTP-Authentifizierung fehlgeschlagen - Prüfe Email/Passwort in config.json"
                self.logger.log_error(error_msg, exception=e)
                return (False, error_msg)

            except smtplib.SMTPException as e:
                # Allgemeiner SMTP-Fehler
                last_error = str(e)
                self.logger.log_warning(f"SMTP-Fehler beim Versuch {attempt + 1}: {e}")

                # Warte vor erneutem Versuch (außer beim letzten Versuch)
                if attempt < retry_count - 1:
                    time.sleep(retry_delay)

            except Exception as e:
                # Sonstiger Fehler
                last_error = str(e)
                self.logger.log_error(f"Unerwarteter Fehler beim Email-Versand", exception=e)

                if attempt < retry_count - 1:
                    time.sleep(retry_delay)

        # Alle Versuche fehlgeschlagen
        return (False, f"Email-Versand nach {retry_count} Versuchen fehlgeschlagen: {last_error}")

    def send_notification_email(self, recipient_email, subject, message):
        """
        Sendet eine einfache Benachrichtigungs-Email (ohne Anhänge).
        Nützlich für System-Benachrichtigungen oder Warnungen.

        Args:
            recipient_email (str): Empfänger-Email
            subject (str): Email-Betreff
            message (str): Nachrichtentext

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            # Erstelle Email-Nachricht
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = recipient_email
            msg['Subject'] = subject

            # Füge Text hinzu
            msg.attach(MIMEText(message, 'plain', 'utf-8'))

            # Sende Email
            return self._send_email(msg)

        except Exception as e:
            self.logger.log_error("Fehler beim Senden der Benachrichtigungs-Email", exception=e)
            return (False, f"Fehler: {str(e)}")

    def send_system_alert(self, alert_type, details):
        """
        Sendet eine System-Warnung an den Administrator.

        Args:
            alert_type (str): Art der Warnung (z.B. "Speicher voll", "GPS-Fehler")
            details (str): Detail-Informationen zur Warnung

        Returns:
            tuple: (success: bool, message: str)
        """
        # Admin-Email aus Config holen (falls vorhanden)
        admin_email = self.config.get('admin_email', self.sender_email)

        subject = f"⚠️ System-Warnung: {alert_type}"

        message = f"""
        System-Warnung vom Raspberry Pi Kamera-System

        Typ: {alert_type}
        Zeit: {self.utils.get_current_datetime_formatted()}

        Details:
        {details}

        Bitte prüfen Sie das System.

        ---
        Automatisch generiert von Raspberry Pi Kamera-System
        """

        return self.send_notification_email(admin_email, subject, message)

    def test_smtp_connection(self):
        """
        Testet die SMTP-Verbindung ohne Email zu senden.
        Nützlich zum Überprüfen der Konfiguration.

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            self.logger.log_info("Teste SMTP-Verbindung...")

            # Verbinde mit SMTP-Server
            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10)

            if self.use_tls:
                server.starttls()

            # Versuche Login
            server.login(self.sender_email, self.sender_password)

            # Schließe Verbindung
            server.quit()

            self.logger.log_info("SMTP-Verbindung erfolgreich getestet")
            return (True, "SMTP-Verbindung erfolgreich")

        except smtplib.SMTPAuthenticationError:
            error_msg = "Authentifizierung fehlgeschlagen - Falsches Passwort oder App-Passwort erforderlich"
            self.logger.log_error(error_msg)
            return (False, error_msg)

        except Exception as e:
            self.logger.log_error("SMTP-Verbindungstest fehlgeschlagen", exception=e)
            return (False, f"Fehler: {str(e)}")

    def get_smtp_status(self):
        """
        Gibt den aktuellen Status der SMTP-Konfiguration zurück.

        Returns:
            dict: Status-Informationen
        """
        is_configured = (
                self.sender_email != "PLATZHALTER@outlook.com" and
                self.sender_password != "PLATZHALTER_PASSWORT"
        )

        return {
            'configured': is_configured,
            'smtp_server': self.smtp_server,
            'smtp_port': self.smtp_port,
            'sender_email': self.sender_email if is_configured else "Nicht konfiguriert",
            'use_tls': self.use_tls,
            'password_set': self.sender_password != "PLATZHALTER_PASSWORT"
        }


# ============================================================================
# Beispiel-Verwendung (wird nur ausgeführt wenn Datei direkt gestartet wird)
# ============================================================================
if __name__ == "__main__":
    import sys

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from modules.logger import SystemLogger
    from modules.utils import SystemUtils

    # Test
