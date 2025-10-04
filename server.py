import asyncio
import json
import sqlite3
import hashlib
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from camera_stream import MotionCameraStream

# ---------------------------------------
# Globale Variablen
# ---------------------------------------
pcs = set()
relay = MediaRelay()
camera = MotionCameraStream(camera_index=0, target_size=(1280, 720))
DB_PATH = "users.db"

# ---------------------------------------
# Datenbank Setup
# ---------------------------------------
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
    print("✅ Datenbank initialisiert:", DB_PATH)

def hash_pw(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

def check_user(username: str, password: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if not row:
        print(f"❌ Login fehlgeschlagen: {username} (kein Eintrag gefunden)")
        return False
    valid = row[0] == hash_pw(password)
    print(f"{'✅' if valid else '❌'} Login {'erfolgreich' if valid else 'fehlgeschlagen'}: {username}")
    return valid

def create_user(username: str, password: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hash_pw(password)))
        conn.commit()
        print(f"✅ Neuer Benutzer angelegt: {username}")
        return True
    except sqlite3.IntegrityError:
        print(f"❌ Benutzername bereits vergeben: {username}")
        return False
    except Exception as e:
        print(f"⚠️ Fehler beim Anlegen von Benutzer '{username}': {e}")
        return False
    finally:
        conn.close()

# ---------------------------------------
# API ROUTES
# ---------------------------------------

async def login(request):
    data = await request.json()
    username = data.get("username", "")
    password = data.get("password", "")
    if check_user(username, password):
        return web.Response(status=200, text="OK")
    return web.Response(status=403, text="Wrong credentials")

async def register(request):
    data = await request.json()
    username = data.get("username", "")
    password = data.get("password", "")

    if not username or not password:
        return web.Response(status=400, text="Missing fields")

    if create_user(username, password):
        return web.Response(status=200, text="User created")
    return web.Response(status=409, text="User exists")

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

async def index(request):
    return web.FileResponse("templates/index1.html")

async def javascript(request):
    return web.FileResponse("static/js/client1.js")

async def on_shutdown(app):
    camera.stop()
    for pc in pcs:
        await pc.close()
    pcs.clear()
    print("🛑 Server beendet, Kamera gestoppt.")

# ---------------------------------------
# App-Setup
# ---------------------------------------
def create_app():
    print("🚀 Starte VR-Racer Backend...")
    init_db()
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/client1.js", javascript)
    app.router.add_get("/motion", motion_status)
    app.router.add_post("/offer", offer)
    app.router.add_post("/login", login)
    app.router.add_post("/register", register)
    app.router.add_static("/static/", path="static", name="static")
    app.on_shutdown.append(on_shutdown)
    return app

# ---------------------------------------
# Start
# ---------------------------------------
if __name__ == "__main__":
    web.run_app(create_app(), host="192.168.178.159", port=8080)