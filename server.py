#!/usr/bin/env python3
# ======================================================
# 🚀 VR-Racer Backend – Final Stable (2 feste Admins)
# ======================================================

import asyncio
import json
import sqlite3
import hashlib
import os
import jwt
import datetime
import traceback
import threading
from typing import List, Dict, Optional
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from camera_stream import CameraProcess
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# ======================================================
# ⚙️ BASISKONFIGURATION
# ======================================================
load_dotenv()

pcs = set()
relay = MediaRelay()
camera_manager = None
STREAM_BACKEND = os.getenv("STREAM_BACKEND", "go2rtc").lower()  # "go2rtc" (default) or "python"


def _parse_size(raw: str, default=(1280, 720)):
    try:
        w, h = raw.lower().split("x", 1)
        return int(w), int(h)
    except Exception:
        return default


def _parse_bool(raw: str, default: bool = True) -> bool:
    if raw is None:
        return default
    return raw.lower() not in ("0", "false", "no", "off")


CAMERA_SIZE = _parse_size(os.getenv("CAMERA_SIZE", "1280x720"))
CAMERA_MAX_FPS = os.getenv("CAMERA_MAX_FPS")
CAMERA_MAX_FPS = float(CAMERA_MAX_FPS) if CAMERA_MAX_FPS else None
CAMERA_USE_ALL_CORES = _parse_bool(os.getenv("CAMERA_USE_ALL_CORES", "1"), True)
CAMERA_SWAP_RB = _parse_bool(os.getenv("CAMERA_SWAP_RB", "0"), False)
CAMERA_BUFFER_COUNT = int(os.getenv("CAMERA_BUFFER_COUNT", "2"))
CAMERA_QUEUE = _parse_bool(os.getenv("CAMERA_QUEUE", "0"), False)
CAMERA_PIXEL_FORMAT = os.getenv("CAMERA_FORMAT", "RGB888")
CAMERA_FRAME_FORMAT = os.getenv("VIDEO_FRAME_FORMAT", "rgb24")
CAMERA_COLOR_CONVERT = os.getenv("CAMERA_COLOR_CONVERT", "auto")
CAMERA_TEST_PATTERN = _parse_bool(os.getenv("CAMERA_TEST_PATTERN", "0"), False)
CAMERA_RIGHT_INDEX = int(os.getenv("CAMERA_RIGHT_INDEX", "0"))
CAMERA_LEFT_INDEX = int(os.getenv("CAMERA_LEFT_INDEX", "1"))


class CameraManager:
    def __init__(self, relay: MediaRelay, target_size=(1280, 720), sensitivity=40):
        self._relay = relay
        self._target_size = target_size
        self._sensitivity = sensitivity
        self._lock = threading.Lock()
        self._vr_clients = 0

        print(
            f"🎥 Camera cfg: size={target_size[0]}x{target_size[1]} "
            f"fmt={CAMERA_PIXEL_FORMAT} frame={CAMERA_FRAME_FORMAT} "
            f"swap_rb={int(CAMERA_SWAP_RB)} buffers={CAMERA_BUFFER_COUNT} "
            f"queue={int(CAMERA_QUEUE)} max_fps={CAMERA_MAX_FPS} "
            f"convert={CAMERA_COLOR_CONVERT} test={int(CAMERA_TEST_PATTERN)} "
            f"right_idx={CAMERA_RIGHT_INDEX} left_idx={CAMERA_LEFT_INDEX}"
        )
        self.camera_right_proc = CameraProcess(
            camera_index=CAMERA_RIGHT_INDEX,
            target_size=target_size,
            max_fps=CAMERA_MAX_FPS,
            use_all_cores=CAMERA_USE_ALL_CORES,
            pixel_format=CAMERA_PIXEL_FORMAT,
            frame_format=CAMERA_FRAME_FORMAT,
            swap_rb=CAMERA_SWAP_RB,
            color_convert=CAMERA_COLOR_CONVERT,
            test_pattern=CAMERA_TEST_PATTERN,
            buffer_count=CAMERA_BUFFER_COUNT,
            queue=CAMERA_QUEUE,
        )
        self.camera_right_track = self.camera_right_proc.create_track()

        self.camera_left_proc = None
        self.camera_left_track = None

    def acquire_vr(self):
        with self._lock:
            if self.camera_left_proc is None:
                self.camera_left_proc = CameraProcess(
                    camera_index=CAMERA_LEFT_INDEX,
                    target_size=self._target_size,
                    max_fps=CAMERA_MAX_FPS,
                    use_all_cores=CAMERA_USE_ALL_CORES,
                    pixel_format=CAMERA_PIXEL_FORMAT,
                    frame_format=CAMERA_FRAME_FORMAT,
                    swap_rb=CAMERA_SWAP_RB,
                    color_convert=CAMERA_COLOR_CONVERT,
                    test_pattern=CAMERA_TEST_PATTERN,
                    buffer_count=CAMERA_BUFFER_COUNT,
                    queue=CAMERA_QUEUE,
                )
                self.camera_left_track = self.camera_left_proc.create_track()
            self._vr_clients += 1

    def release_vr(self):
        with self._lock:
            if self._vr_clients > 0:
                self._vr_clients -= 1
            if self._vr_clients == 0:
                if self.camera_left_proc:
                    self.camera_left_proc.stop()
                    self.camera_left_proc = None
                    self.camera_left_track = None

    def get_tracks(self, vr_mode: bool):
        track_right = self._relay.subscribe(self.camera_right_track)
        if not vr_mode:
            return [track_right]
        if self.camera_left_track is None:
            raise RuntimeError("Kamera links ist nicht verfügbar")
        track_left = self._relay.subscribe(self.camera_left_track)
        return [track_left, track_right]

    def stop_all(self):
        if self.camera_right_proc:
            self.camera_right_proc.stop()
            self.camera_right_proc = None
        if self.camera_left_proc:
            self.camera_left_proc.stop()
            self.camera_left_proc = None
        self.camera_left_track = None



DB_PATH = "users.db"
KEY_FILE = "secret.key"

JWT_SECRET = os.getenv("JWT_SECRET", "fallback_secret_key")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
ADMIN_G_PASS = os.getenv("ADMIN_G_PASS", "admin123")
ADMIN_D_PASS = os.getenv("ADMIN_D_PASS", "admin123")


def configure_multicore():
    cpu_count = os.cpu_count() or 1
    try:
        os.sched_setaffinity(0, set(range(cpu_count)))
        print(f"⚙️ CPU-Affinität gesetzt: {cpu_count} Kerne")
    except (AttributeError, PermissionError, OSError):
        pass

# ======================================================
# 🔐 HASH & VERSCHLÜSSELUNG
# ======================================================

def hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def load_key() -> bytes:
    """Erzeugt automatisch einen neuen Key, wenn keiner vorhanden ist"""
    try:
        with open(KEY_FILE, "rb") as f:
            return f.read()
    except FileNotFoundError:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        print("🔐 Neuer Encryption-Key erzeugt:", KEY_FILE)
        return key

fernet = Fernet(load_key())

# ======================================================
# 🗄️ DATENBANK
# ======================================================

def ensure_is_admin_column(c: sqlite3.Cursor):
    try:
        c.execute("SELECT is_admin FROM users LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    """)
    ensure_is_admin_column(c)
    conn.commit()

    # 🔐 Admins aus .env laden
    admins = {
        "Admin_G": ADMIN_G_PASS,
        "Admin_D": ADMIN_D_PASS
    }

    # Bestehende User abrufen
    c.execute("SELECT username FROM users")
    rows = c.fetchall()
    existing_names = set()

    for (enc_name,) in rows:
        try:
            name = fernet.decrypt(enc_name.encode()).decode()
            existing_names.add(name)
        except Exception:
            continue

    # 🔁 Admins hinzufügen, wenn sie fehlen
    for name, pw in admins.items():
        if not pw:
            print(f"⚠️ Kein Passwort für {name} in .env gefunden – wird übersprungen.")
            continue
        if name not in existing_names:
            enc_user = fernet.encrypt(name.encode()).decode()
            c.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
                (enc_user, hash_pw(pw)),
            )
            print(f"👑 Admin '{name}' neu erstellt.")
        else:
            print(f"✅ Admin '{name}' existiert bereits – wird nicht neu erstellt.")

    conn.commit()
    conn.close()
    print(f"✅ Datenbank initialisiert: {DB_PATH}")

# ======================================================
# 👥 BENUTZERFUNKTIONEN
# ======================================================

def username_exists(username: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username FROM users")
    rows = c.fetchall()
    conn.close()
    for (enc_name,) in rows:
        try:
            if fernet.decrypt(enc_name.encode()).decode().lower() == username.lower():
                return True
        except Exception:
            pass
    return False

def create_user(username: str, password: str) -> bool:
    if username_exists(username):
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        enc = fernet.encrypt(username.encode()).decode()
        c.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 0)",
            (enc, hash_pw(password)),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def check_user(username: str, password: str) -> Dict[str, bool]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username, password_hash, is_admin FROM users")
    rows = c.fetchall()
    conn.close()
    for enc_name, pw_hash, is_admin in rows:
        try:
            if fernet.decrypt(enc_name.encode()).decode() == username and pw_hash == hash_pw(password):
                return {"ok": True, "admin": bool(is_admin)}
        except Exception:
            continue
    return {"ok": False, "admin": False}

def get_all_users() -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, username, is_admin FROM users ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()
    users = []
    for uid, enc_name, is_admin in rows:
        try:
            name = fernet.decrypt(enc_name.encode()).decode()
        except Exception:
            name = "⚠️ Unlesbar"
        users.append({"id": uid, "username": name, "is_admin": bool(is_admin)})
    return users

def delete_user(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username, is_admin FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False

    enc_name, is_admin = row
    try:
        name = fernet.decrypt(enc_name.encode()).decode()
    except Exception:
        name = ""

    # Admins dürfen nicht gelöscht werden
    if name in ("Admin_G", "Admin_D") or is_admin == 1:
        conn.close()
        print(f"🚫 Versuch, Admin '{name}' zu löschen – blockiert.")
        return False

    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    deleted = c.rowcount > 0
    conn.close()
    return deleted

def update_user(user_id: int, new_username: Optional[str], new_password: Optional[str]) -> (bool, str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username, is_admin FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "not_found"

    enc_name, is_admin = row
    try:
        name = fernet.decrypt(enc_name.encode()).decode()
    except Exception:
        name = ""

    # Admins sperren
    if name in ("Admin_G", "Admin_D") or is_admin == 1:
        conn.close()
        print(f"🚫 Versuch, Admin '{name}' zu ändern – blockiert.")
        return False, "admin_locked"

    if new_username:
        if username_exists(new_username):
            conn.close()
            return False, "name_exists"
        enc = fernet.encrypt(new_username.encode()).decode()
        c.execute("UPDATE users SET username = ? WHERE id = ?", (enc, user_id))

    if new_password:
        c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_pw(new_password), user_id))

    conn.commit()
    conn.close()
    return True, "ok"

# ======================================================
# 🔑 JWT AUTHENTIFIZIERUNG
# ======================================================

def create_token(username: str, is_admin: bool) -> str:
    exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"user": username, "is_admin": is_admin, "exp": exp}
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return token if isinstance(token, str) else token.decode("utf-8")

def decode_token(token: str):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

def require_auth(request: web.Request, admin_required: bool = False):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    tkn = auth.split(" ")[1]
    data = decode_token(tkn)
    if not data:
        return None
    if admin_required and not data.get("is_admin"):
        return None
    return data

# ======================================================
# 🌐 API-ENDPUNKTE
# ======================================================

async def login(request: web.Request) -> web.Response:
    data = await request.json()
    username = data.get("username", "")
    password = data.get("password", "")
    result = check_user(username, password)
    if result["ok"]:
        token = create_token(username, result["admin"])
        return web.json_response({
            "token": token,
            "expires_in": JWT_EXPIRE_MINUTES * 60
        }, status=202 if result["admin"] else 200)
    return web.Response(status=403, text="Wrong credentials")

async def register(request: web.Request) -> web.Response:
    data = await request.json()
    username = data.get("username", "")
    password = data.get("password", "")
    if username_exists(username):
        return web.Response(status=409, text="User exists")
    if create_user(username, password):
        return web.Response(status=200, text="User created")
    return web.Response(status=500, text="Error creating user")

async def ping(request: web.Request) -> web.Response:
    return web.Response(status=204)

async def offer(request: web.Request) -> web.Response:
    if STREAM_BACKEND != "python":
        return web.Response(status=503, text="Streaming disabled (go2rtc mode)")
    user = require_auth(request)
    if not user:
        return web.Response(status=401, text="Unauthorized")

    try:
        params = await request.json()
        vr_mode = bool(params.get("vr", False))
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
        pc = RTCPeerConnection()
        pcs.add(pc)
        pc.is_vr = vr_mode

        if vr_mode:
            camera_manager.acquire_vr()

        @pc.on("connectionstatechange")
        async def on_state_change():
            if pc.connectionState in ("failed", "closed", "disconnected"):
                await pc.close()
                if getattr(pc, "is_vr", False):
                    camera_manager.release_vr()
                pcs.discard(pc)

        await pc.setRemoteDescription(offer)
        for track in camera_manager.get_tracks(vr_mode):
            pc.addTrack(track)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return web.json_response({
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type
        })
    except Exception:
        print("💥 [offer] Fehler:\n" + traceback.format_exc())
        if 'vr_mode' in locals() and vr_mode:
            camera_manager.release_vr()
        return web.Response(status=500, text="Offer error")

# ======================================================
# 👑 ADMIN-ENDPUNKTE
# ======================================================

async def admin_users(request: web.Request) -> web.Response:
    auth_data = require_auth(request, admin_required=True)
    if not auth_data:
        return web.Response(status=401, text="Unauthorized")
    try:
        users = get_all_users()
        return web.json_response(users)
    except Exception:
        print("💥 Fehler bei /admin/users:\n" + traceback.format_exc())
        return web.Response(status=500, text="Server error")

async def admin_delete(request: web.Request) -> web.Response:
    if not require_auth(request, admin_required=True):
        return web.Response(status=401, text="Unauthorized")
    data = await request.json()
    user_id = data.get("id")
    if user_id is None:
        return web.Response(status=400, text="Invalid request")
    if delete_user(int(user_id)):
        return web.Response(status=200, text="User deleted")
    return web.Response(status=404, text="User not found or admin")

async def admin_update(request: web.Request) -> web.Response:
    if not require_auth(request, admin_required=True):
        return web.Response(status=401, text="Unauthorized")
    data = await request.json()
    user_id = data.get("id")
    new_name = (data.get("username") or "").strip()
    new_pass = (data.get("password") or "").strip()
    if user_id is None or (not new_name and not new_pass):
        return web.Response(status=400, text="Invalid request")
    ok, reason = update_user(int(user_id), new_name if new_name else None, new_pass if new_pass else None)
    if ok:
        return web.Response(status=200, text="Updated")
    if reason == "admin_locked":
        return web.Response(status=403, text="Admin locked")
    if reason == "name_exists":
        return web.Response(status=409, text="Name exists")
    return web.Response(status=404, text="User not found")

# ======================================================
# 🌍 ROUTEN UND SERVER-SETUP
# ======================================================

async def index(request: web.Request) -> web.Response:
    return web.FileResponse("templates/index1.html")

async def javascript(request: web.Request) -> web.Response:
    return web.FileResponse("static/js/client1.js")

async def dashboard(request: web.Request) -> web.Response:
    return web.FileResponse("templates/dashboard.html")

async def on_shutdown(app: web.Application):
    if camera_manager:
        camera_manager.stop_all()
    for pc in list(pcs):
        await pc.close()
    pcs.clear()
    print("📷 Kamera gestoppt")
    print("🛑 Server beendet.")

def create_app() -> web.Application:
    global camera_manager
    init_db()
    if STREAM_BACKEND == "python":
        if camera_manager is None:
            camera_manager = CameraManager(relay, target_size=CAMERA_SIZE)
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/dashboard", dashboard)
    app.router.add_get("/client1.js", javascript)
    app.router.add_get("/ping", ping)
    app.router.add_post("/login", login)
    app.router.add_post("/register", register)
    if STREAM_BACKEND == "python":
        app.router.add_post("/offer", offer)
    app.router.add_get("/admin/users", admin_users)
    app.router.add_post("/admin/delete", admin_delete)
    app.router.add_post("/admin/update", admin_update)
    app.router.add_static("/static/", path="static", name="static")
    app.on_shutdown.append(on_shutdown)
    return app

if __name__ == "__main__":
    print("🚀 Starte VR-Racer ")
    configure_multicore()
    web.run_app(create_app(), host="0.0.0.0", port=8080)
