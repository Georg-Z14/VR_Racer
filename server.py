import asyncio
import json
import sqlite3
import hashlib
import os
from typing import List, Dict, Optional
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from camera_stream import MotionCameraStream
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# ======================================================
# ⚙️ BASIS
# ======================================================

load_dotenv()  # .env laden
pcs = set()
relay = MediaRelay()
camera = MotionCameraStream(camera_index=0, target_size=(1280, 720))

DB_PATH = "users.db"
KEY_FILE = "secret.key"

# ======================================================
# 🔐 HASH & VERSCHLÜSSELUNG
# ======================================================

def hash_pw(password: str) -> str:
    """Sicherer Hash mit SHA256"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def load_key() -> bytes:
    """Lädt oder erzeugt AES-Verschlüsselungs-Key für Usernamen"""
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
    """Falls alte DB ohne is_admin existiert -> Spalte nachrüsten."""
    try:
        c.execute("SELECT is_admin FROM users LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")

def init_db():
    """Initialisiert die Datenbank und legt Admins aus .env an"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    ensure_is_admin_column(c)
    conn.commit()

    # Admins aus .env laden
    admins = {
        "Admin_G": os.getenv("ADMIN_G_PASS"),
        "Admin_D": os.getenv("ADMIN_D_PASS")
    }

    for name, pw in admins.items():
        if not pw:
            print(f"⚠️ Kein Passwort in .env für {name} gefunden – übersprungen.")
            continue

        # Existiert schon?
        c.execute("SELECT username FROM users")
        rows = c.fetchall()
        exists = False
        for (enc,) in rows:
            try:
                if fernet.decrypt(enc.encode()).decode() == name:
                    exists = True
                    break
            except Exception:
                continue

        if not exists:
            enc_user = fernet.encrypt(name.encode()).decode()
            c.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
                (enc_user, hash_pw(pw)),
            )
            print(f"👑 Admin hinzugefügt: {name}")

    conn.commit()
    conn.close()
    print(f"✅ Datenbank initialisiert: {DB_PATH}")

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
        print(f"✅ Benutzer erstellt: {username}")
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
    """Löscht nur normale Benutzer (nicht Admins)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ? AND is_admin = 0", (user_id,))
    conn.commit()
    deleted = c.rowcount > 0
    conn.close()
    return deleted

def update_user(user_id: int, new_username: Optional[str], new_password: Optional[str]) -> (bool, str):
    """Aktualisiert normale Benutzer; Admins sind geschützt."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "not_found"
    if row[0] == 1:
        conn.close()
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
# 🌐 API
# ======================================================

async def login(request: web.Request) -> web.Response:
    data = await request.json()
    username = data.get("username", "")
    password = data.get("password", "")
    result = check_user(username, password)

    if result["ok"]:
        if result["admin"]:
            print(f"👑 Admin-Login: {username}")
            return web.Response(status=202, text="admin")
        print(f"✅ Login erfolgreich: {username}")
        return web.Response(status=200, text="OK")

    print(f"❌ Login fehlgeschlagen: {username}")
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

async def offer(request: web.Request) -> web.Response:
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_state_change():
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await pc.close()
            pcs.discard(pc)

    await pc.setRemoteDescription(offer)
    track = relay.subscribe(camera)
    pc.addTrack(track)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

async def motion_status(request: web.Request) -> web.Response:
    return web.json_response({"motion": bool(camera.motion_detected)})

async def admin_users(request: web.Request) -> web.Response:
    return web.json_response(get_all_users())

async def admin_delete(request: web.Request) -> web.Response:
    data = await request.json()
    user_id = data.get("id")
    if user_id is None:
        return web.Response(status=400, text="Invalid request")
    if delete_user(int(user_id)):
        return web.Response(status=200, text="User deleted")
    return web.Response(status=404, text="User not found or admin")

async def admin_update(request: web.Request) -> web.Response:
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

async def index(request: web.Request) -> web.Response:
    return web.FileResponse("templates/index1.html")

async def javascript(request: web.Request) -> web.Response:
    return web.FileResponse("static/js/client1.js")

# ======================================================
# 🧹 SHUTDOWN
# ======================================================

async def on_shutdown(app: web.Application):
    camera.stop()
    for pc in list(pcs):
        await pc.close()
    pcs.clear()
    print("📷 Kamera gestoppt")
    print("🛑 Server beendet.")

# ======================================================
# 🚀 START
# ======================================================

def create_app() -> web.Application:
    init_db()
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/client1.js", javascript)
    app.router.add_get("/motion", motion_status)
    app.router.add_post("/offer", offer)
    app.router.add_post("/login", login)
    app.router.add_post("/register", register)
    app.router.add_get("/admin/users", admin_users)
    app.router.add_post("/admin/delete", admin_delete)
    app.router.add_post("/admin/update", admin_update)
    app.router.add_static("/static/", path="static", name="static")
    app.on_shutdown.append(on_shutdown)
    return app

if __name__ == "__main__":
    print("🚀 Starte VR-Racer Backend...")
    web.run_app(create_app(), host="192.168.178.159", port=8080)