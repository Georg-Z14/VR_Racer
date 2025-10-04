import asyncio
import json
import sqlite3
import hashlib
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from camera_stream import MotionCameraStream
from cryptography.fernet import Fernet

# ======================================================
# ⚙️ GRUNDKONFIGURATION
# ======================================================

pcs = set()
relay = MediaRelay()
camera = MotionCameraStream(camera_index=0, target_size=(1280, 720))
DB_PATH = "users.db"
KEY_FILE = "secret.key"

# ======================================================
# 🔐 VERSCHLÜSSELUNG
# ======================================================

def load_key():
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

def hash_pw(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

# ======================================================
# 🗄️ DATENBANK
# ======================================================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    print(f"✅ Datenbank initialisiert: {DB_PATH}")

def username_exists(username: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username FROM users")
    rows = c.fetchall()
    conn.close()
    for enc_user, in rows:
        try:
            if fernet.decrypt(enc_user.encode()).decode().lower() == username.lower():
                return True
        except:
            pass
    return False

def create_user(username: str, password: str) -> bool:
    if username_exists(username):
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        enc = fernet.encrypt(username.encode()).decode()
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                  (enc, hash_pw(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def check_user(username: str, password: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username, password_hash FROM users")
    rows = c.fetchall()
    conn.close()
    for enc_user, pw_hash in rows:
        try:
            if fernet.decrypt(enc_user.encode()).decode() == username and pw_hash == hash_pw(password):
                return True
        except:
            pass
    return False

def get_all_users():
    """Entschlüsselte Benutzernamen zurückgeben."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, username FROM users")
    rows = c.fetchall()
    conn.close()
    users = []
    for uid, enc_name in rows:
        try:
            users.append({"id": uid, "username": fernet.decrypt(enc_name.encode()).decode()})
        except:
            continue
    return users

def delete_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    print(f"🗑️ Benutzer gelöscht: ID={user_id}")

# ======================================================
# 🌐 API
# ======================================================

async def login(request):
    data = await request.json()
    username = data.get("username", "")
    password = data.get("password", "")
    if check_user(username, password):
        if username == "admin":
            return web.Response(status=202, text="admin")
        return web.Response(status=200, text="OK")
    return web.Response(status=403, text="Wrong credentials")

async def register(request):
    data = await request.json()
    username = data.get("username", "")
    password = data.get("password", "")
    if username_exists(username):
        return web.Response(status=409, text="User exists")
    if create_user(username, password):
        return web.Response(status=200, text="User created")
    return web.Response(status=500, text="Error creating user")

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection()
    pcs.add(pc)
    await pc.setRemoteDescription(offer)
    track = relay.subscribe(camera)
    pc.addTrack(track)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

async def motion_status(request):
    return web.json_response({"motion": bool(camera.motion_detected)})

# --- Admin API ---
async def admin_users(request):
    return web.json_response(get_all_users())

async def admin_delete(request):
    data = await request.json()
    user_id = data.get("id")
    if user_id is not None:
        delete_user(user_id)
        return web.Response(status=200, text="User deleted")
    return web.Response(status=400, text="Invalid request")

async def index(request):
    return web.FileResponse("templates/index1.html")

async def javascript(request):
    return web.FileResponse("static/js/client1.js")

# ======================================================
# 🧹 SHUTDOWN
# ======================================================

async def on_shutdown(app):
    camera.stop()
    for pc in pcs:
        await pc.close()
    pcs.clear()
    print("📷 Kamera gestoppt")
    print("🛑 Server beendet.")

# ======================================================
# 🚀 START
# ======================================================

def create_app():
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
    app.router.add_static("/static/", path="static", name="static")
    app.on_shutdown.append(on_shutdown)
    return app

if __name__ == "__main__":
    print("🚀 Starte VR-Racer Backend...")
    web.run_app(create_app(), host="192.168.178.159", port=8080)