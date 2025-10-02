import asyncio
import json
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from camera_stream import CameraStream

pcs = set()
relay = MediaRelay()   # Relay-Instanz erzeugen
camera = CameraStream()  # nur einmal erzeugen!

# 🔑 Festes Passwort
ADMIN_PASSWORD = "Hallo123!"

# ---------- Offer ----------
async def offer(request):
    # Passwort prüfen
    pw = request.headers.get("Authorization", "")
    if pw != ADMIN_PASSWORD:
        return web.Response(status=403, text="Unauthorized")

    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    await pc.setRemoteDescription(offer)

    # Kamera-Stream mit Relay teilen
    pc.addTrack(relay.subscribe(camera))

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response(
        {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
    )

# ---------- Login ----------
async def login(request):
    data = await request.json()
    if data.get("password") == ADMIN_PASSWORD:
        return web.Response(status=200, text="OK")
    return web.Response(status=403, text="Wrong password")

# ---------- Static ----------
async def index(request):
    return web.FileResponse("index1.html")

async def javascript(request):
    return web.FileResponse("client1.js")

# ---------- Shutdown ----------
async def on_shutdown(app):
    for pc in pcs:
        await pc.close()
    pcs.clear()

# ---------- App ----------
def create_app():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/client1.js", javascript)
    app.router.add_post("/offer", offer)
    app.router.add_post("/login", login)
    app.router.add_static("/static/", path="static", name="static")
    app.on_shutdown.append(on_shutdown)
    return app

if __name__ == "__main__":
    web.run_app(create_app(), host="172.20.10.3", port=8080)  # für Freunde erreichbar