#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
Hauptprogramm WebRTC-Version - Raspberry Pi 5 Kamera-Streaming-System
Datei: main_webrtc.py
Version: 1.0
Datum: 30.09.2025

Funktionen:
- Flask Web-Server mit HTTPS
- WebRTC-Streaming (niedrige Latenz ~100-300ms, beste Qualität)
- Account-basierte Authentifizierung
- Unterschiedliche Berechtigungen für User und Admins
- Video-Aufnahme mit Speicher-Check
- GPS-Integration mit Echtzeit-Tracking
- Email-Versand von Aufnahmen
- Automatischer SFTP-Upload
- aiortc für WebRTC-Implementierung
============================================================================
Modul 9 Web-Server WebRTC 
===========================================================================

"""

import os
import sys
import json
import threading
import time
import asyncio
from datetime import datetime
from flask import Flask, render_template, Response, request, redirect, url_for, jsonify, session, send_file
from flask_cors import CORS
import ssl

# WebRTC-spezifische Imports
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaPlayer, MediaRecorder
from av import VideoFrame
import numpy as np
from PIL import Image

# Importiere eigene Module (identisch mit MJPEG-Version)
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
logger.log_info("RASPBERRY PI 5 KAMERA-STREAMING-SYSTEM (WebRTC)")
logger.log_info("=" * 70)

# Initialisiere Hilfsfunktionen
utils = SystemUtils(config, logger)

# Initialisiere Flask-App
app = Flask(__name__)
app.secret_key = config['session']['secret_key']
CORS(app)  # CORS für WebRTC-Signaling notwendig

# Initialisiere Module (identisch mit MJPEG-Version)
logger.log_info("Initialisiere System-Module...")
auth_manager = AuthManager(os.path.join(config['paths']['database'], 'accounts.db'), logger)
camera = CameraController(config, logger)
gps = GPSController(config, logger)
email_sender = EmailSender(config, logger, utils)
sftp_uploader = SFTPUploader(config, logger)

# Globale Variablen
current_recording = None
recording_lock = threading.Lock()

# WebRTC-spezifische Variablen
peer_connections = set()  # Speichert aktive WebRTC-Verbindungen
webrtc_lock = threading.Lock()

logger.log_info("System erfolgreich initialisiert")

# Zeige System-Informationen
sys_info = utils.get_system_info()
logger.log_info(f"Hostname: {sys_info['hostname']}")
logger.log_info(f"IP-Adresse: {sys_info['ip_address']}")
logger.log_info(f"CPU-Temperatur: {sys_info['cpu_temp']}°C")


# ============================================================================
# WebRTC VIDEO TRACK
# ============================================================================

class CameraVideoTrack(VideoStreamTrack):
    """
    Custom Video Track für WebRTC-Streaming.
    Holt kontinuierlich Frames von der Raspberry Pi Kamera.
    """

    def __init__(self, camera_controller):
        """
        Initialisiert den Video-Track.

        Args:
            camera_controller: CameraController-Instanz
        """
        super().__init__()  # Initialisiere Basis-Klasse
        self.camera = camera_controller
        self.logger = logger

        # Frame-Rate Kontrolle
        self.frame_count = 0
        self.start_time = time.time()

    async def recv(self):
        """
        Holt das nächste Video-Frame.
        Diese Methode wird kontinuierlich von aiortc aufgerufen.

        Returns:
            VideoFrame: Frame für WebRTC-Stream
        """
        try:
            # Hole aktuelles Frame von Kamera als NumPy-Array
            frame_data = self.camera.camera.capture_array()

            # Konvertiere NumPy-Array zu PIL-Image
            pil_image = Image.fromarray(frame_data)

            # Konvertiere PIL-Image zu VideoFrame für WebRTC
            video_frame = VideoFrame.from_image(pil_image)

            # Setze Presentation Timestamp (wichtig für Synchronisation)
            pts, time_base = await self.next_timestamp()
            video_frame.pts = pts
            video_frame.time_base = time_base

            # Frame-Zähler für Statistiken
            self.frame_count += 1

            # Logge FPS alle 100 Frames
            if self.frame_count % 100 == 0:
                elapsed = time.time() - self.start_time
                fps = self.frame_count / elapsed if elapsed > 0 else 0
                self.logger.log_debug(f"WebRTC Stream: {fps:.1f} fps")

            return video_frame

        except Exception as e:
            self.logger.log_error("Fehler beim Abrufen des Kamera-Frames für WebRTC", exception=e)

            # Erstelle schwarzes Fallback-Frame bei Fehler
            black_frame = Image.new('RGB', (640, 480), color='black')
            video_frame = VideoFrame.from_image(black_frame)
            pts, time_base = await self.next_timestamp()
            video_frame.pts = pts
            video_frame.time_base = time_base

            return video_frame


# ============================================================================
# HILFSFUNKTIONEN FÜR AUTHENTIFIZIERUNG (identisch mit MJPEG)
# ============================================================================

def require_login(f):
    """Decorator: Prüft ob Benutzer eingeloggt ist."""

    def decorated_function(*args, **kwargs):
        session_token = session.get('session_token')

        if not session_token:
            return redirect(url_for('login'))

        user_info = auth_manager.verify_session(session_token)

        if not user_info:
            session.clear()
            return redirect(url_for('login'))

        request.user_info = user_info
        return f(*args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function


def require_admin(f):
    """Decorator: Prüft ob Benutzer Admin-Rechte hat."""

    def decorated_function(*args, **kwargs):
        session_token = session.get('session_token')

        if not session_token:
            return jsonify({'error': 'Nicht eingeloggt'}), 401

        user_info = auth_manager.verify_session(session_token)

        if not user_info:
            return jsonify({'error': 'Session ungültig'}), 401

        if not user_info.get('is_admin', False):
            return jsonify({'error': 'Admin-Rechte erforderlich'}), 403

        request.user_info = user_info
        return f(*args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function


# ============================================================================
# ROUTEN: AUTHENTIFIZIERUNG (identisch mit MJPEG)
# ============================================================================

@app.route('/')
def index():
    """Startseite - leitet zu Login oder Dashboard."""
    session_token = session.get('session_token')

    if session_token:
        user_info = auth_manager.verify_session(session_token)
        if user_info:
            if user_info['is_admin']:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))

    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login-Seite."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user_info = auth_manager.authenticate_user(username, password)

        if user_info:
            session['session_token'] = user_info['session_token']
            session['username'] = user_info['username']
            session['is_admin'] = user_info['is_admin']

            logger.log_access(username, 'Login', ip_address=request.remote_addr)

            if user_info['is_admin']:
                session['show_admin_popup'] = True
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        else:
            logger.log_access(username, 'Login fehlgeschlagen', ip_address=request.remote_addr)
            return render_template('login.html', error='Falscher Benutzername oder Passwort')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Logout."""
    session_token = session.get('session_token')
    username = session.get('username', 'Unbekannt')

    if session_token:
        auth_manager.logout_user(session_token)

    logger.log_access(username, 'Logout', ip_address=request.remote_addr)
    session.clear()

    return redirect(url_for('login'))


# ============================================================================
# ROUTEN: DASHBOARDS (identisch mit MJPEG)
# ============================================================================

@app.route('/user/dashboard')
@require_login
def user_dashboard():
    """Dashboard für normale Benutzer."""
    user_info = request.user_info

    gps_data = None
    if gps.is_connected:
        gps_data = gps.get_current_position()

    tracking_stats = None
    if gps.is_tracking:
        tracking_stats = gps.get_tracking_stats()

    return render_template(
        'user_dashboard.html',
        username=user_info['username'],
        gps_data=gps_data,
        tracking_stats=tracking_stats,
        gps_enabled=config['gps']['enabled'],
        stream_type='webrtc'  # Unterschied zu MJPEG-Version
    )


@app.route('/admin/dashboard')
@require_admin
def admin_dashboard():
    """Dashboard für Administratoren."""
    user_info = request.user_info

    sys_info = utils.get_system_info()
    storage = utils.check_disk_space()
    camera_settings = camera.get_current_settings()

    gps_status = {
        'enabled': gps.gps_enabled,
        'connected': gps.is_connected,
        'tracking': gps.is_tracking
    }

    sftp_status = sftp_uploader.get_sftp_status()
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
        current_recording=current_recording,
        stream_type='webrtc'  # Unterschied zu MJPEG-Version
    )


# ============================================================================
# ROUTEN: ADMIN-FUNKTIONEN (identisch mit MJPEG)
# ============================================================================

@app.route('/admin/start-recording', methods=['POST'])
@require_admin
def admin_start_recording():
    """Admin startet Video-Aufnahme."""
    global current_recording

    with recording_lock:
        if current_recording and camera.is_recording:
            return jsonify({'error': 'Aufnahme läuft bereits'}), 400

        storage = utils.check_disk_space()
        if storage and storage['warning']:
            warning_msg = utils.get_storage_warning_message()
            return jsonify({'error': 'Speicher zu voll', 'warning': warning_msg}), 507

        recording_path = utils.generate_full_recording_path()

        gps_data = None
        if gps.is_connected:
            gps_data = gps.get_current_position()

        if gps.gps_enabled and not gps.is_tracking:
            gps.start_tracking()

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
    """Admin stoppt Video-Aufnahme."""
    global current_recording

    with recording_lock:
        success, message, recording_stats = camera.stop_recording()

        if not success:
            return jsonify({'error': message}), 400

        if gps.is_tracking:
            gps_success, gps_msg, gps_stats = gps.stop_tracking()

            if gps_success and gps.track_points:
                track_filename = os.path.basename(current_recording['path']).replace('.mp4', '_track.gpx')
                track_path = os.path.join(config['paths']['gps_tracks'], track_filename)
                gps.export_gpx(track_path)

        if current_recording:
            current_recording['stats'] = recording_stats
            recording_path = current_recording['path']

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
    """Admin ändert Kamera-Einstellungen."""
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
    """Admin listet alle Aufnahmen auf."""
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
    """Admin lädt Aufnahme herunter."""
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
    """Admin löscht Aufnahme."""
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
    """Admin listet alle Benutzer auf."""
    users = auth_manager.get_all_users()
    return jsonify({'users': users})


@app.route('/admin/create-user', methods=['POST'])
@require_admin
def admin_create_user():
    """Admin erstellt neuen Benutzer."""
    username = request.json.get('username')
    password = request.json.get('password')
    is_admin = request.json.get('is_admin', False)
    email = request.json.get('email')

    success, message = auth_manager.create_user(username, password, is_admin, email)

    if success:
        logger.log_access(
            request.user_info['username'],
            'Benutzer erstellt',
            ip_address=request.remote_addr,
            details=f"Neuer User: {username}, Admin: {is_admin}"
        )
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'error': message}), 400


@app.route('/admin/delete-user', methods=['POST'])
@require_admin
def admin_delete_user():
    """Admin löscht Benutzer."""
    username = request.json.get('username')

    success, message = auth_manager.delete_user(username)

    if success:
        logger.log_access(
            request.user_info['username'],
            'Benutzer gelöscht',
            ip_address=request.remote_addr,
            details=f"Gelöscht: {username}"
        )
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'error': message}), 400


@app.route('/admin/system-logs')
@require_admin
def admin_system_logs():
    """Admin holt System-Log-Statistiken."""
    log_stats = logger.get_log_stats()
    return jsonify({'logs': log_stats})


@app.route('/admin/system-restart', methods=['POST'])
@require_admin
def admin_system_restart():
    """Admin startet System neu."""
    logger.log_access(
        request.user_info['username'],
        'System-Neustart initiiert',
        ip_address=request.remote_addr
    )

    camera.cleanup()
    gps.disconnect()

    # Für WebRTC-Version: camera_webrtc.service
    os.system('sudo systemctl restart camera_webrtc.service')

    return jsonify({'success': True, 'message': 'System wird neu gestartet...'})


@app.route('/admin/system-shutdown', methods=['POST'])
@require_admin
def admin_system_shutdown():
    """Admin fährt System herunter."""
    logger.log_access(
        request.user_info['username'],
        'System-Herunterfahren initiiert',
        ip_address=request.remote_addr
    )

    camera.cleanup()
    gps.disconnect()

    os.system('sudo shutdown -h now')

    return jsonify({'success': True, 'message': 'System wird heruntergefahren...'})


# ============================================================================
# ROUTEN: WebRTC-SIGNALING
# ============================================================================

@app.route('/webrtc/offer', methods=['POST'])
@require_login
async def webrtc_offer():
    """
    WebRTC-Signaling: Verarbeitet Offer vom Client.
    Erstellt PeerConnection und sendet Answer zurück.
    """
    try:
        params = request.get_json()
        offer = RTCSessionDescription(sdp=params['sdp'], type=params['type'])

        logger.log_access(
            request.user_info['username'],
            'WebRTC-Stream-Verbindung angefordert',
            ip_address=request.remote_addr
        )

        # Erstelle neue PeerConnection
        pc = RTCPeerConnection()

        with webrtc_lock:
            peer_connections.add(pc)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            """Callback bei Änderung des Verbindungsstatus."""
            logger.log_info(f"WebRTC Verbindungsstatus: {pc.connectionState}")

            if pc.connectionState == "failed" or pc.connectionState == "closed":
                await pc.close()
                with webrtc_lock:
                    peer_connections.discard(pc)

        # Füge Video-Track hinzu
        video_track = CameraVideoTrack(camera)
        pc.addTrack(video_track)

        # Verarbeite Offer und erstelle Answer
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return jsonify({
            'sdp': pc.localDescription.sdp,
            'type': pc.localDescription.type
        })

    except Exception as e:
        logger.log_error("Fehler beim WebRTC-Signaling", exception=e)
        return jsonify({'error': str(e)}), 500


@app.route('/webrtc/close', methods=['POST'])
@require_login
async def webrtc_close():
    """
    Schließt alle WebRTC-Verbindungen des Clients.
    """
    try:
        # Schließe alle aktiven PeerConnections
        with webrtc_lock:
            for pc in list(peer_connections):
                await pc.close()
            peer_connections.clear()

        logger.log_access(
            request.user_info['username'],
            'WebRTC-Stream beendet',
            ip_address=request.remote_addr
        )

        return jsonify({'success': True})

    except Exception as e:
        logger.log_error("Fehler beim Schließen der WebRTC-Verbindung", exception=e)
        return jsonify({'error': str(e)}), 500


# ============================================================================
# API-ROUTEN (identisch mit MJPEG)
# ============================================================================

@app.route('/api/gps/position')
@require_login
def api_gps_position():
    """API: Aktuelle GPS-Position."""
    if not gps.is_connected:
        return jsonify({'error': 'GPS nicht verbunden'}), 503

    position = gps.get_current_position()

    if position:
        return jsonify(position)
    else:
        return jsonify({'error': 'Kein GPS-Fix'}), 503


@app.route('/api/gps/track')
@require_login
def api_gps_track():
    """API: Aktuelle GPS-Route."""
    if not gps.is_tracking:
        return jsonify({'error': 'Kein Tracking aktiv'}), 400

    return jsonify({
        'tracking': True,
        'points': gps.track_points,
        'stats': gps.get_tracking_stats()
    })


@app.route('/api/recording/status')
@require_login
def api_recording_status():
    """API: Status der aktuellen Aufnahme."""
    if not camera.is_recording:
        return jsonify({'recording': False})

    duration_info = camera.get_recording_duration()

    return jsonify({
        'recording': True,
        'duration': duration_info
    })


@app.route('/api/system/status')
@require_login
def api_system_status():
    """API: Allgemeiner System-Status."""
    status = {
        'camera': camera.get_current_settings(),
        'gps': {
            'enabled': gps.gps_enabled,
            'connected': gps.is_connected,
            'tracking': gps.is_tracking
        },
        'storage': utils.check_disk_space(),
        'recording': camera.is_recording,
        'stream_type': 'webrtc'  # Unterschied zu MJPEG
    }

    if request.user_info.get('is_admin', False):
        status['ip_address'] = sys_info['ip_address']
        status['cpu_temp'] = sys_info['cpu_temp']

    return jsonify(status)


@app.route('/user/request-recording', methods=['POST'])
@require_login
def request_recording():
    """Normal-User fordert Aufnahme per Email an."""
    user_info = request.user_info

    email = request.form.get('email')

    if not email:
        return jsonify({'error': 'Keine Email-Adresse angegeben'}), 400

    if not current_recording:
        return jsonify({'error': 'Keine Aufnahme verfügbar'}), 400

    recording_path = current_recording.get('path')
    recording_stats = current_recording.get('stats')

    if not os.path.exists(recording_path):
        return jsonify({'error': 'Aufnahme-Datei nicht gefunden'}), 404

    map_screenshot_path = None
    if gps.is_tracking and gps.track_points:
        map_screenshot_path = os.path.join(
            config['paths']['recordings'],
            f"map_{user_info['username']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )
        success, msg = utils.create_map_screenshot(gps.track_points, map_screenshot_path)
        if not success:
            map_screenshot_path = None

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
# FEHLERBEHANDLUNG
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """404 Fehler."""
    return render_template('error.html', error_code=404, message='Seite nicht gefunden'), 404


@app.errorhandler(500)
def internal_error(error):
    """500 Fehler."""
    logger.log_error("Interner Server-Fehler", exception=error)
    return render_template('error.html', error_code=500, message='Interner Server-Fehler'), 500


@app.errorhandler(403)
def forbidden(error):
    """403 Fehler."""
    return render_template('error.html', error_code=403, message='Zugriff verweigert'), 403


# ============================================================================
# HAUPTPROGRAMM
# ============================================================================

async def cleanup_peer_connections():
    """
    Schließt alle WebRTC-Verbindungen beim Herunterfahren.
    """
    with webrtc_lock:
        for pc in list(peer_connections):
            await pc.close()
        peer_connections.clear()


if __name__ == '__main__':
    try:
        server_host = config['server']['host']
        server_port = config['server']['port']
        ssl_cert = config['server']['ssl_cert']
        ssl_key = config['server']['ssl_key']

        logger.log_info(f"Starte WebRTC HTTPS-Server auf {server_host}:{server_port}")
        logger.log_info(f"Zugriff über: https://{sys_info['ip_address']}:{server_port}")
        logger.log_info("WebRTC bietet niedrige Latenz (~100-300ms)")

        # Erstelle SSL-Context für HTTPS
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(ssl_cert, ssl_key)

        # Starte Flask-Server mit HTTPS
        app.run(
            host=server_host,
            port=server_port,
            ssl_context=ssl_context,
            threaded=True,
            debug=False
        )

    except KeyboardInterrupt:
        logger.log_info("Server wird beendet (Keyboard Interrupt)...")

    except Exception as e:
        logger.log_critical("Kritischer Fehler beim Starten des Servers", exception=e)

    finally:
        logger.log_info("Führe Cleanup durch...")

        # Cleanup WebRTC-Verbindungen
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(cleanup_peer_connections())
        loop.close()

        # Cleanup Module
        camera.cleanup()
        gps.disconnect()
        sftp_uploader.disconnect()

        logger.log_info("System beendet")
