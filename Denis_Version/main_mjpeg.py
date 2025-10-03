#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
Hauptprogramm MJPEG-Version - Raspberry Pi 5 Kamera-Streaming-System
Datei: main_mjpeg.py
Version: 1.0
Datum: 30.09.2025

Funktionen:
- Flask Web-Server mit HTTPS
- MJPEG-Streaming (höhere Kompatibilität, alle Browser)
- Account-basierte Authentifizierung
- Unterschiedliche Berechtigungen für User und Admins
- Video-Aufnahme mit Speicher-Check
- GPS-Integration mit Echtzeit-Tracking
- Email-Versand von Aufnahmen
- Automatischer SFTP-Upload
- Logging und Fehlerbehandlung
============================================================================
Modul 8 - Web-Server MJPEG Version 
============================================================================

"""

import os
import sys
import json
import threading
import time
from datetime import datetime
from flask import Flask, render_template, Response, request, redirect, url_for, jsonify, session, send_file
from flask_cors import CORS
import ssl

# Importiere eigene Module
from modules.auth import AuthManager
from modules.camera import CameraController
from modules.gps import GPSController
from modules.email_sender import EmailSender
from modules.sftp_uploader import SFTPUploader
from modules.logger import SystemLogger
from modules.utils import SystemUtils

# ============================================================================
# GLOBALE KONFIGURATION
# ============================================================================

# Pfade
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'config.json')

# Lade Konfiguration aus config.json
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    config = json.load(f)

# Initialisiere Logger
logger = SystemLogger(config['paths']['logs'])
logger.log_info("=" * 70)
logger.log_info("RASPBERRY PI 5 KAMERA-STREAMING-SYSTEM (MJPEG)")
logger.log_info("=" * 70)

# Initialisiere Hilfsfunktionen
utils = SystemUtils(config, logger)

# Initialisiere Flask-App
app = Flask(__name__)
app.secret_key = config['session']['secret_key']  # Für Session-Management
CORS(app)  # Aktiviere CORS für API-Zugriffe

# Initialisiere Module
logger.log_info("Initialisiere System-Module...")
auth_manager = AuthManager(os.path.join(config['paths']['database'], 'accounts.db'), logger)
camera = CameraController(config, logger)
gps = GPSController(config, logger)
email_sender = EmailSender(config, logger, utils)
sftp_uploader = SFTPUploader(config, logger)

# Globale Variablen
current_recording = None  # Speichert Info über aktuelle Aufnahme
recording_lock = threading.Lock()  # Thread-sicherer Zugriff auf Aufnahme-Status

logger.log_info("System erfolgreich initialisiert")

# Zeige System-Informationen
sys_info = utils.get_system_info()
logger.log_info(f"Hostname: {sys_info['hostname']}")
logger.log_info(f"IP-Adresse: {sys_info['ip_address']}")
logger.log_info(f"CPU-Temperatur: {sys_info['cpu_temp']}°C")


# ============================================================================
# HILFSFUNKTIONEN FÜR AUTHENTIFIZIERUNG
# ============================================================================

def require_login(f):
    """
    Decorator: Prüft ob Benutzer eingeloggt ist.
    Leitet zu Login-Seite weiter wenn nicht eingeloggt.
    """

    def decorated_function(*args, **kwargs):
        # Prüfe ob Session-Token vorhanden
        session_token = session.get('session_token')

        if not session_token:
            return redirect(url_for('login'))

        # Verifiziere Session-Token
        user_info = auth_manager.verify_session(session_token)

        if not user_info:
            # Session ungültig - lösche und leite zu Login
            session.clear()
            return redirect(url_for('login'))

        # Füge User-Info zu Request hinzu für Zugriff in Route
        request.user_info = user_info

        return f(*args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function


def require_admin(f):
    """
    Decorator: Prüft ob Benutzer Admin-Rechte hat.
    Gibt 403 Fehler zurück wenn kein Admin.
    """

    def decorated_function(*args, **kwargs):
        # Prüfe ob Session-Token vorhanden
        session_token = session.get('session_token')

        if not session_token:
            return jsonify({'error': 'Nicht eingeloggt'}), 401

        # Verifiziere Session-Token
        user_info = auth_manager.verify_session(session_token)

        if not user_info:
            return jsonify({'error': 'Session ungültig'}), 401

        # Prüfe Admin-Status
        if not user_info.get('is_admin', False):
            return jsonify({'error': 'Admin-Rechte erforderlich'}), 403

        # Füge User-Info zu Request hinzu
        request.user_info = user_info

        return f(*args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function


# ============================================================================
# ROUTEN: AUTHENTIFIZIERUNG
# ============================================================================

@app.route('/')
def index():
    """
    Startseite - leitet zu Login oder Stream weiter je nach Login-Status.
    """
    session_token = session.get('session_token')

    if session_token:
        user_info = auth_manager.verify_session(session_token)
        if user_info:
            # Benutzer eingeloggt - leite zu passendem Dashboard
            if user_info['is_admin']:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))

    # Nicht eingeloggt - zeige Login-Seite
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Login-Seite mit Account-Erstellung (nur durch Admins).
    """
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Authentifiziere Benutzer
        user_info = auth_manager.authenticate_user(username, password)

        if user_info:
            # Login erfolgreich - speichere Session
            session['session_token'] = user_info['session_token']
            session['username'] = user_info['username']
            session['is_admin'] = user_info['is_admin']

            # Logge Zugriff
            logger.log_access(
                username,
                'Login',
                ip_address=request.remote_addr
            )

            # Zeige Admin-Popup falls Admin
            if user_info['is_admin']:
                session['show_admin_popup'] = True
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        else:
            # Login fehlgeschlagen
            logger.log_access(
                username,
                'Login fehlgeschlagen',
                ip_address=request.remote_addr
            )
            return render_template('login.html', error='Falscher Benutzername oder Passwort')

    # GET-Request - zeige Login-Formular
    return render_template('login.html')


@app.route('/logout')
def logout():
    """
    Logout - beendet Session und leitet zu Login.
    """
    session_token = session.get('session_token')
    username = session.get('username', 'Unbekannt')

    if session_token:
        auth_manager.logout_user(session_token)

    logger.log_access(username, 'Logout', ip_address=request.remote_addr)

    # Lösche Session
    session.clear()

    return redirect(url_for('login'))


# ============================================================================
# ROUTEN: BENUTZER-DASHBOARD
# ============================================================================

@app.route('/user/dashboard')
@require_login
def user_dashboard():
    """
    Dashboard für normale Benutzer.
    Zeigt Live-Stream, GPS-Daten und Fahrtzeit.
    """
    user_info = request.user_info

    # Hole aktuelle GPS-Daten falls verfügbar
    gps_data = None
    if gps.is_connected:
        gps_data = gps.get_current_position()

    # Hole Tracking-Statistiken falls aktiv
    tracking_stats = None
    if gps.is_tracking:
        tracking_stats = gps.get_tracking_stats()

    return render_template(
        'user_dashboard.html',
        username=user_info['username'],
        gps_data=gps_data,
        tracking_stats=tracking_stats,
        gps_enabled=config['gps']['enabled']
    )


@app.route('/user/request-recording', methods=['POST'])
@require_login
def request_recording():
    """
    Normal-User kann Aufnahme per Email anfordern.
    """
    user_info = request.user_info

    # Hole User-Email aus Datenbank
    # (Für diese Funktion muss User Email-Adresse hinterlegt haben)
    email = request.form.get('email')

    if not email:
        return jsonify({'error': 'Keine Email-Adresse angegeben'}), 400

    # Prüfe ob aktuelle Aufnahme existiert
    if not current_recording:
        return jsonify({'error': 'Keine Aufnahme verfügbar'}), 400

    recording_path = current_recording.get('path')
    recording_stats = current_recording.get('stats')

    if not os.path.exists(recording_path):
        return jsonify({'error': 'Aufnahme-Datei nicht gefunden'}), 404

    # Erstelle GPS-Karten-Screenshot falls GPS aktiv
    map_screenshot_path = None
    if gps.is_tracking and gps.track_points:
        map_screenshot_path = os.path.join(
            config['paths']['recordings'],
            f"map_{user_info['username']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )
        success, msg = utils.create_map_screenshot(
            gps.track_points,
            map_screenshot_path
        )
        if not success:
            map_screenshot_path = None

    # Sende Email
    logger.log_info(f"User {user_info['username']} fordert Aufnahme per Email an: {email}")

    success, message = email_sender.send_recording_email(
        email,
        user_info['username'],
        recording_path,
        recording_stats,
        map_screenshot_path
    )

    if success:
        logger.log_access(
            user_info['username'],
            'Aufnahme per Email angefordert',
            ip_address=request.remote_addr,
            details=f"Email: {email}"
        )
        return jsonify({'success': True, 'message': 'Email wird versendet'})
    else:
        return jsonify({'error': f'Email-Versand fehlgeschlagen: {message}'}), 500


# ============================================================================
# ROUTEN: ADMIN-DASHBOARD
# ============================================================================

@app.route('/admin/dashboard')
@require_admin
def admin_dashboard():
    """
    Dashboard für Administratoren.
    Zeigt alle Funktionen und System-Status.
    """
    user_info = request.user_info

    # Hole System-Informationen
    sys_info = utils.get_system_info()

    # Hole Speicherplatz-Info
    storage = utils.check_disk_space()

    # Hole Kamera-Einstellungen
    camera_settings = camera.get_current_settings()

    # Hole GPS-Status
    gps_status = {
        'enabled': gps.gps_enabled,
        'connected': gps.is_connected,
        'tracking': gps.is_tracking
    }

    # Hole SFTP-Status
    sftp_status = sftp_uploader.get_sftp_status()

    # Prüfe ob Admin-Popup angezeigt werden soll
    show_admin_popup = session.pop('show_admin_popup', False)

    return render_template(
        'admin.html',
        username=user_info['username'],
        sys_info=sys_info,
        storage=storage,
        camera_settings=camera_settings,
        gps_status=gps_status,
        sftp_status=sftp_status,
        show_admin_popup=show_admin_popup,
        current_recording=current_recording
    )


@app.route('/admin/start-recording', methods=['POST'])
@require_admin
def admin_start_recording():
    """
    Admin startet Video-Aufnahme.
    """
    global current_recording

    with recording_lock:
        # Prüfe ob bereits Aufnahme läuft
        if current_recording and camera.is_recording:
            return jsonify({'error': 'Aufnahme läuft bereits'}), 400

        # Prüfe Speicherplatz
        storage = utils.check_disk_space()
        if storage and storage['warning']:
            warning_msg = utils.get_storage_warning_message()
            return jsonify({'error': 'Speicher zu voll', 'warning': warning_msg}), 507

        # Generiere Dateinamen
        recording_path = utils.generate_full_recording_path()

        # Hole GPS-Daten falls verfügbar
        gps_data = None
        if gps.is_connected:
            gps_data = gps.get_current_position()

        # Starte GPS-Tracking falls aktiviert und noch nicht aktiv
        if gps.gps_enabled and not gps.is_tracking:
            gps.start_tracking()

        # Starte Aufnahme
        success, message, recording_info = camera.start_recording(recording_path, gps_data)

        if success:
            current_recording = {
                'path': recording_path,
                'info': recording_info,
                'start_time': datetime.now()
            }

            logger.log_access(
                request.user_info['username'],
                'Aufnahme gestartet',
                ip_address=request.remote_addr,
                details=f"Datei: {os.path.basename(recording_path)}"
            )

            return jsonify({
                'success': True,
                'message': message,
                'filename': os.path.basename(recording_path)
            })
        else:
            return jsonify({'error': message}), 500


@app.route('/admin/stop-recording', methods=['POST'])
@require_admin
def admin_stop_recording():
    """
    Admin stoppt Video-Aufnahme.
    """
    global current_recording

    with recording_lock:
        # Stoppe Aufnahme
        success, message, recording_stats = camera.stop_recording()

        if not success:
            return jsonify({'error': message}), 400

        # Stoppe GPS-Tracking
        if gps.is_tracking:
            gps_success, gps_msg, gps_stats = gps.stop_tracking()

            # Exportiere GPS-Track
            if gps_success and gps.track_points:
                track_filename = os.path.basename(current_recording['path']).replace('.mp4', '_track.gpx')
                track_path = os.path.join(config['paths']['gps_tracks'], track_filename)
                gps.export_gpx(track_path)

        # Update current_recording mit Stats
        if current_recording:
            current_recording['stats'] = recording_stats
            recording_path = current_recording['path']

            # Automatischer SFTP-Upload wenn aktiviert
            if sftp_uploader.auto_upload and sftp_uploader.sftp_enabled:
                logger.log_info("Starte automatischen SFTP-Upload...")
                upload_success, upload_msg, upload_info = sftp_uploader.upload_recording(recording_path)

                if upload_success:
                    logger.log_info(f"Aufnahme erfolgreich hochgeladen: {upload_msg}")
                else:
                    logger.log_warning(f"SFTP-Upload fehlgeschlagen: {upload_msg}")

        logger.log_access(
            request.user_info['username'],
            'Aufnahme gestoppt',
            ip_address=request.remote_addr,
            details=f"Dauer: {recording_stats['duration_formatted']}, Größe: {recording_stats['file_size_mb']} MB"
        )

        return jsonify({
            'success': True,
            'message': message,
            'stats': recording_stats
        })


@app.route('/admin/camera-settings', methods=['POST'])
@require_admin
def admin_camera_settings():
    """
    Admin ändert Kamera-Einstellungen (Helligkeit, Kontrast, Zoom).
    """
    setting = request.json.get('setting')
    value = request.json.get('value')

    if setting == 'brightness':
        success = camera.set_brightness(float(value))
    elif setting == 'contrast':
        success = camera.set_contrast(float(value))
    elif setting == 'zoom':
        success = camera.set_zoom(float(value))
    else:
        return jsonify({'error': 'Unbekannte Einstellung'}), 400

    if success:
        logger.log_access(
            request.user_info['username'],
            f'Kamera-Einstellung geändert: {setting}',
            ip_address=request.remote_addr,
            details=f"Wert: {value}"
        )
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Fehler beim Setzen der Einstellung'}), 500


@app.route('/admin/recordings')
@require_admin
def admin_recordings():
    """
    Admin listet alle Aufnahmen auf.
    """
    recordings_path = config['recording']['save_path']

    recordings = []
    if os.path.exists(recordings_path):
        for filename in sorted(os.listdir(recordings_path), reverse=True):
            if filename.endswith('.mp4'):
                file_path = os.path.join(recordings_path, filename)
                file_info = utils.get_file_info(file_path)
                if file_info:
                    recordings.append(file_info)

    return jsonify({'recordings': recordings})


@app.route('/admin/download/<filename>')
@require_admin
def admin_download(filename):
    """
    Admin lädt Aufnahme herunter.
    """
    recordings_path = config['recording']['save_path']
    file_path = os.path.join(recordings_path, filename)

    if not os.path.exists(file_path):
        return jsonify({'error': 'Datei nicht gefunden'}), 404

    logger.log_access(
        request.user_info['username'],
        'Aufnahme heruntergeladen',
        ip_address=request.remote_addr,
        details=f"Datei: {filename}"
    )

    return send_file(file_path, as_attachment=True)


@app.route('/admin/delete-recording', methods=['POST'])
@require_admin
def admin_delete_recording():
    """
    Admin löscht Aufnahme.
    """
    filename = request.json.get('filename')

    recordings_path = config['recording']['save_path']
    file_path = os.path.join(recordings_path, filename)

    if not os.path.exists(file_path):
        return jsonify({'error': 'Datei nicht gefunden'}), 404

    try:
        os.remove(file_path)

        logger.log_access(
            request.user_info['username'],
            'Aufnahme gelöscht',
            ip_address=request.remote_addr,
            details=f"Datei: {filename}"
        )

        return jsonify({'success': True, 'message': 'Aufnahme gelöscht'})

    except Exception as e:
        logger.log_error(f"Fehler beim Löschen der Aufnahme: {filename}", exception=e)
        return jsonify({'error': str(e)}), 500


@app.route('/admin/users')
@require_admin
def admin_users():
    """
    Admin listet alle Benutzer auf.
    """
