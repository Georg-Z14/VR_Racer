#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
Account-Verwaltungsmodul für Raspberry Pi 5 Kamera-Streaming-System
Datei: modules/auth.py
Version: 1.0
Datum: 30.09.2025

Funktionen:
- Benutzer-Authentifizierung mit SQLite-Datenbank
- Passwort-Hashing mit SHA-256 und Salt
- Session-Management (2h für User, unbegrenzt für Admins)
- Account-Erstellung nur durch Admins
- Zwei fest definierte Admin-Accounts
============================================================================
Modul 2 - Account-Verwaltungsmodul
============================================================================

"""

import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
import os
import logging


class AuthManager:
    """
    Hauptklasse für die Verwaltung von Benutzer-Accounts und Authentifizierung.
    Unterstützt normale Benutzer und Administratoren mit unterschiedlichen Rechten.
    """

    def __init__(self, db_path):
        """
        Initialisiert die Account-Verwaltung und erstellt die Datenbank.

        Args:
            db_path (str): Vollständiger Pfad zur SQLite-Datenbank-Datei
                          Beispiel: /home/pi/camera_system/database/accounts.db
        """
        self.db_path = db_path  # Speichere Datenbank-Pfad für spätere Verwendung
        self.logger = logging.getLogger('AuthManager')  # Logger für Fehlerprotokollierung

        # Initialisiere die Datenbank (erstellt Tabellen falls nicht vorhanden)
        self.init_database()

        # Erstelle die zwei fest definierten Admin-Accounts
        self.create_default_admins()

    def init_database(self):
        """
        Erstellt die SQLite-Datenbank und die 'users'-Tabelle falls sie nicht existieren.
        Die Tabelle enthält alle notwendigen Felder für Benutzer-Verwaltung.
        """
        # Stelle sicher, dass das Datenbank-Verzeichnis existiert
        db_dir = os.path.dirname(self.db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            self.logger.info(f"Datenbank-Verzeichnis erstellt: {db_dir}")

        # Verbinde mit SQLite-Datenbank (wird automatisch erstellt falls nicht vorhanden)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Erstelle Benutzer-Tabelle mit allen notwendigen Spalten
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                email TEXT,
                session_token TEXT,
                session_expires TIMESTAMP
            )
        ''')

        # Speichere Änderungen und schließe Verbindung
        conn.commit()
        conn.close()

        self.logger.info("Datenbank initialisiert")

    def create_default_admins(self):
        """
        Erstellt die zwei fest definierten Admin-Accounts beim ersten Start.
        Diese Accounts können nicht gelöscht werden und sind immer verfügbar.

        Admin 1: Admin_G mit Passwort 'admin1234'
        Admin 2: Admin_D mit Passwort '123456789'
        """
        # Erstelle Admin_G (oder aktualisiere falls bereits vorhanden)
        self.create_user(
            username="Admin_G",
            password="admin1234",
            is_admin=True,
            force_create=True  # Überschreibt existierenden Account
        )

        # Erstelle Admin_D (oder aktualisiere falls bereits vorhanden)
        self.create_user(
            username="Admin_D",
            password="123456789",
            is_admin=True,
            force_create=True  # Überschreibt existierenden Account
        )

        self.logger.info("Standard-Admin-Accounts erstellt/aktualisiert")

    def hash_password(self, password):
        """
        Erstellt einen sicheren Hash des Passworts mit zufälligem Salt.
        Das Salt macht jeden Hash einzigartig, selbst bei identischen Passwörtern.

        Args:
            password (str): Passwort im Klartext

        Returns:
            str: Gehashtes Passwort im Format 'hash:salt'
        """
        # Generiere 16-Byte zufälliges Salt (32 Hex-Zeichen)
        salt = secrets.token_hex(16)

        # Kombiniere Passwort mit Salt
        password_salt = password + salt

        # Erstelle SHA-256 Hash der Kombination
        hashed = hashlib.sha256(password_salt.encode('utf-8')).hexdigest()

        # Speichere Hash und Salt zusammen (getrennt durch Doppelpunkt)
        # Format: hash:salt ermöglicht spätere Verifizierung
        return f"{hashed}:{salt}"

    # ============================================================
    # ALTERNATIVE: Passwort-Hashing mit bcrypt (auskommentiert)
    # Für erhöhte Sicherheit kann bcrypt verwendet werden
    # ============================================================
    # import bcrypt
    # def hash_password_bcrypt(self, password):
    #     """Hashte Passwort mit bcrypt (sicherer, aber langsamer)"""
    #     salt = bcrypt.gensalt()
    #     hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    #     return hashed.decode('utf-8')
    #
    # def verify_password_bcrypt(self, password, password_hash):
    #     """Verifiziere Passwort mit bcrypt"""
    #     return bcrypt.checkpw(
    #         password.encode('utf-8'),
    #         password_hash.encode('utf-8')
    #     )
    # ============================================================

    def verify_password(self, password, password_hash):
        """
        Überprüft ob ein eingegebenes Passwort mit dem gespeicherten Hash übereinstimmt.

        Args:
            password (str): Eingegebenes Passwort im Klartext
            password_hash (str): Gespeicherter Hash aus Datenbank (Format: hash:salt)

        Returns:
            bool: True wenn Passwort korrekt, False wenn falsch oder Fehler
        """
        try:
            # Trenne den gespeicherten Hash in Hash und Salt
            stored_hash, salt = password_hash.split(':')

            # Hashe das eingegebene Passwort mit demselben Salt
            password_salt = password + salt
            calculated_hash = hashlib.sha256(password_salt.encode('utf-8')).hexdigest()

            # Vergleiche die beiden Hashes
            # Timing-sicherer Vergleich verhindert Timing-Attacken
            return secrets.compare_digest(calculated_hash, stored_hash)

        except Exception as e:
            # Bei Fehler (z.B. falsches Format) gebe False zurück
            self.logger.error(f"Fehler bei Passwort-Verifizierung: {e}")
            return False

    def create_user(self, username, password, is_admin=False, email=None, force_create=False):
        """
        Erstellt einen neuen Benutzer-Account in der Datenbank.
        Nur Admins dürfen diese Funktion aufrufen (wird im Web-Server geprüft).

        Args:
            username (str): Gewünschter Benutzername (muss eindeutig sein)
            password (str): Passwort im Klartext (wird gehasht gespeichert)
            is_admin (bool): True für Admin-Rechte, False für normale Benutzer
            email (str): Optional - Email-Adresse des Benutzers
            force_create (bool): True um bestehende Benutzer zu überschreiben

        Returns:
            tuple: (success: bool, message: str)
                  - (True, "Account erstellt") bei Erfolg
                  - (False, "Fehlermeldung") bei Fehler
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Prüfe ob Benutzername bereits existiert
            cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
            existing_user = cursor.fetchone()

            if existing_user and not force_create:
                conn.close()
                return (False, f"Benutzername '{username}' existiert bereits")

            # Hashe das Passwort sicher
            password_hash = self.hash_password(password)

            if existing_user and force_create:
                # Aktualisiere bestehenden Benutzer
                cursor.execute('''
                    UPDATE users 
                    SET password_hash = ?, is_admin = ?, email = ?
                    WHERE username = ?
                ''', (password_hash, is_admin, email, username))

                self.logger.info(f"Benutzer aktualisiert: {username} (Admin: {is_admin})")
                message = f"Benutzer '{username}' wurde aktualisiert"

            else:
                # Füge neuen Benutzer hinzu
                cursor.execute('''
                    INSERT INTO users (username, password_hash, is_admin, email)
                    VALUES (?, ?, ?, ?)
                ''', (username, password_hash, is_admin, email))

                self.logger.info(f"Neuer Benutzer erstellt: {username} (Admin: {is_admin})")
                message = f"Benutzer '{username}' wurde erfolgreich erstellt"

            conn.commit()
            conn.close()
            return (True, message)

        except sqlite3.IntegrityError as e:
            # Fehler bei Eindeutigkeit (z.B. doppelter Benutzername)
            conn.close()
            self.logger.error(f"Integritätsfehler beim Erstellen von Benutzer {username}: {e}")
            return (False, f"Benutzername '{username}' existiert bereits")

        except Exception as e:
            # Allgemeiner Fehler
            conn.close()
            self.logger.error(f"Fehler beim Erstellen des Benutzers {username}: {e}")
            return (False, f"Fehler beim Erstellen des Benutzers: {str(e)}")

    def authenticate_user(self, username, password):
        """
        Authentifiziert einen Benutzer und erstellt eine neue Session.
        Überprüft Benutzername und Passwort gegen die Datenbank.

        Args:
            username (str): Eingegebener Benutzername
            password (str): Eingegebenes Passwort

        Returns:
            dict: Benutzer-Informationen bei Erfolg, None bei Fehler
                  {
                      'id': int,
                      'username': str,
                      'is_admin': bool,
                      'email': str,
                      'session_token': str,
                      'session_expires': datetime
                  }
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Hole Benutzer-Daten aus Datenbank
            cursor.execute('''
                SELECT id, username, password_hash, is_admin, email 
                FROM users 
                WHERE username = ?
            ''', (username,))

            user_data = cursor.fetchone()

            if not user_data:
                # Benutzer nicht gefunden
                conn.close()
                self.logger.warning(f"Login-Versuch für unbekannten Benutzer: {username}")
                return None

            # Entpacke Benutzer-Daten
            user_id, db_username, password_hash, is_admin, email = user_data

            # Überprüfe Passwort
            if not self.verify_password(password, password_hash):
                # Falsches Passwort
                conn.close()
                self.logger.warning(f"Falsches Passwort für Benutzer: {username}")
                return None

            # Login erfolgreich - erstelle Session-Token
            # Token ist 32 Bytes (256 Bit) zufällige URL-sichere Zeichen
            session_token = secrets.token_urlsafe(32)

            # Berechne Session-Ablaufzeit basierend auf Benutzer-Typ
            if is_admin:
                # Admin-Sessions laufen nie ab (100 Jahre in der Zukunft)
                session_expires = datetime.now() + timedelta(days=36500)
                self.logger.info(f"Admin-Login erfolgreich: {username}")
            else:
                # Normale Benutzer: 2 Stunden Session-Dauer
                session_expires = datetime.now() + timedelta(hours=2)
                self.logger.info(f"User-Login erfolgreich: {username}")

            # Speichere Session in Datenbank und aktualisiere letzten Login
            cursor.execute('''
                UPDATE users 
                SET session_token = ?, 
                    session_expires = ?, 
                    last_login = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (session_token, session_expires.isoformat(), user_id))

            conn.commit()
            conn.close()

            # Gebe Benutzer-Informationen zurück
            return {
                'id': user_id,
                'username': db_username,
                'is_admin': bool(is_admin),
                'email': email,
                'session_token': session_token,
                'session_expires': session_expires
            }

        except Exception as e:
            # Fehler bei der Authentifizierung
            conn.close()
            self.logger.error(f"Fehler bei der Authentifizierung von {username}: {e}")
            return None

    def verify_session(self, session_token):
        """
        Überprüft ob eine Session noch gültig ist.
        Wird bei jedem Seiten-Aufruf aufgerufen um den Login-Status zu prüfen.

        Args:
            session_token (str): Session-Token aus dem Browser-Cookie

        Returns:
            dict: Benutzer-Informationen wenn Session gültig, None wenn ungültig
        """
        if not session_token:
            return None

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Hole Benutzer-Daten basierend auf Session-Token
            cursor.execute('''
                SELECT id, username, is_admin, session_expires 
                FROM users 
                WHERE session_token = ?
            ''', (session_token,))

            user_data = cursor.fetchone()

            if not user_data:
                # Session-Token nicht gefunden
                conn.close()
                return None

            user_id, username, is_admin, session_expires_str = user_data

            # Konvertiere String zu datetime-Objekt
            session_expires = datetime.fromisoformat(session_expires_str)

            # Überprüfe ob Session noch gültig ist
            if datetime.now() > session_expires:
                # Session abgelaufen - lösche sie aus der Datenbank
                cursor.execute('''
                    UPDATE users 
                    SET session_token = NULL, session_expires = NULL 
                    WHERE id = ?
                ''', (user_id,))
                conn.commit()
                conn.close()

                self.logger.info(f"Session abgelaufen für Benutzer: {username}")
                return None

            # Session ist gültig
            conn.close()
            return {
                'id': user_id,
                'username': username,
                'is_admin': bool(is_admin),
                'session_expires': session_expires
            }

        except Exception as e:
            # Fehler bei Session-Überprüfung
            conn.close()
            self.logger.error(f"Fehler bei Session-Überprüfung: {e}")
            return None

    def logout_user(self, session_token):
        """
        Loggt einen Benutzer aus, indem die Session gelöscht wird.

        Args:
            session_token (str): Session-Token des auszuloggenden Benutzers

        Returns:
            bool: True wenn erfolgreich ausgeloggt
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Lösche Session-Token aus der Datenbank
            cursor.execute('''
                UPDATE users 
                SET session_token = NULL, session_expires = NULL 
                WHERE session_token = ?
            ''', (session_token,))

            conn.commit()
            affected_rows = cursor.rowcount
            conn.close()

            if affected_rows > 0:
                self.logger.info(f"Benutzer erfolgreich ausgeloggt")
                return True
            return False

        except Exception as e:
            conn.close()
            self.logger.error(f"Fehler beim Ausloggen: {e}")
            return False

    def get_all_users(self):
        """
        Holt alle Benutzer aus der Datenbank.
        Nur für Admins zugänglich (wird im Web-Server geprüft).

        Returns:
            list: Liste von Benutzer-Dictionaries
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Hole alle Benutzer sortiert nach Erstellungsdatum (neueste zuerst)
            cursor.execute('''
                SELECT id, username, is_admin, created_at, last_login, email
                FROM users 
                ORDER BY created_at DESC
            ''')

            users = []
            for row in cursor.fetchall():
                users.append({
                    'id': row[0],
                    'username': row[1],
                    'is_admin': bool(row[2]),
                    'created_at': row[3],
                    'last_login': row[4],
                    'email': row[5]
                })

            conn.close()
            return users

        except Exception as e:
            conn.close()
            self.logger.error(f"Fehler beim Laden der Benutzer: {e}")
            return []

    def delete_user(self, username):
        """
        Löscht einen Benutzer aus der Datenbank.
        Standard-Admins (Admin_G, Admin_D) können nicht gelöscht werden.
        Nur für Admins zugänglich (wird im Web-Server geprüft).

        Args:
            username (str): Zu löschender Benutzername

        Returns:
            tuple: (success: bool, message: str)
        """
        # Verhindere Löschung der Standard-Admin-Accounts
        if username in ['Admin_G', 'Admin_D']:
            return (False, "Standard-Admin-Accounts können nicht gelöscht werden")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Lösche Benutzer aus der Datenbank
            cursor.execute('DELETE FROM users WHERE username = ?', (username,))
            conn.commit()

            affected_rows = cursor.rowcount
            conn.close()

            if affected_rows > 0:
                self.logger.info(f"Benutzer gelöscht: {username}")
                return (True, f"Benutzer '{username}' wurde gelöscht")
            else:
                return (False, f"Benutzer '{username}' nicht gefunden")

        except Exception as e:
            conn.close()
            self.logger.error(f"Fehler beim Löschen von Benutzer {username}: {e}")
            return (False, f"Fehler beim Löschen: {str(e)}")

    def update_user_email(self, username, email):
        """
        Aktualisiert die Email-Adresse eines Benutzers.

        Args:
            username (str): Benutzername
            email (str): Neue Email-Adresse

        Returns:
            bool: True wenn erfolgreich aktualisiert
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                UPDATE users SET email = ? WHERE username = ?
            ''', (email, username))

            conn.commit()
            affected_rows = cursor.rowcount
            conn.close()

            return affected_rows > 0

        except Exception as e:
            conn.close()
            self.logger.error(f"Fehler beim Aktualisieren der Email für {username}: {e}")
            return False

    def change_password(self, username, new_password):
        """
        Ändert das Passwort eines Benutzers.

        Args:
            username (str): Benutzername
            new_password (str): Neues Passwort im Klartext

        Returns:
            tuple: (success: bool, message: str)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Hashe das neue Passwort
            password_hash = self.hash_password(new_password)

            # Aktualisiere Passwort in der Datenbank
            cursor.execute('''
                UPDATE users SET password_hash = ? WHERE username = ?
            ''', (password_hash, username))

            conn.commit()
            affected_rows = cursor.rowcount
            conn.close()

            if affected_rows > 0:
                self.logger.info(f"Passwort geändert für Benutzer: {username}")
                return (True, "Passwort erfolgreich geändert")
            else:
                return (False, f"Benutzer '{username}' nicht gefunden")

        except Exception as e:
            conn.close()
            self.logger.error(f"Fehler beim Ändern des Passworts für {username}: {e}")
            return (False, f"Fehler beim Ändern des Passworts: {str(e)}")


# ============================================================================
# Beispiel-Verwendung (wird nur ausgeführt wenn Datei direkt gestartet wird)
# ============================================================================
if __name__ == "__main__":
    # Logging konfigurieren für Test-Zwecke
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Erstelle AuthManager mit Test-Datenbank
    auth = AuthManager("/tmp/test_accounts.db")

    # Teste Account-Erstellung
    print("\n=== Test: Account-Erstellung ===")
    success, msg = auth.create_user("TestUser", "testpassword123", is_admin=False, email="test@example.com")
    print(f"Ergebnis: {msg}")

    # Teste Login
    print("\n=== Test: Login ===")
    user_info = auth.authenticate_user("TestUser", "testpassword123")
    if user_info:
        print(f"Login erfolgreich: {user_info['username']} (Admin: {user_info['is_admin']})")
        print(f"Session-Token: {user_info['session_token'][:20]}...")

        # Teste Session-Verifizierung
        print("\n=== Test: Session-Verifizierung ===")
        verified = auth.verify_session(user_info['session_token'])
        if verified:
            print(f"Session gültig für: {verified['username']}")
    else:
        print("Login fehlgeschlagen")

    # Zeige alle Benutzer
    print("\n=== Alle Benutzer ===")
    users = auth.get_all_users()
    for user in users:
        print(f"- {user['username']} (Admin: {user['is_admin']}, Email: {user['email']})")
