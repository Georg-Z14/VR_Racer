import asyncio
import json
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from camera_stream import MotionCameraStream

pcs = set()
relay = MediaRelay()
ADMIN_PASSWORD = "Hallo123!"

# Kamera mit Bewegungserkennung
camera = MotionCameraStream(camera_index=0, target_size=(1280, 720))
QUALITY = "MEDIUM"

QUALITY_PRESETS = {
    "LOW": {"size": (854, 480), "bitrate": 800_000},
    "MEDIUM": {"size": (1280, 720), "bitrate": 1_500_000},
    "HIGH": {"size": (1920, 1080), "bitrate": 3_000_000},
}

pc_senders = {}

# ---------- Offer ----------
async def offer(request):
    pw = request.headers.get("Authorization", "")
    if pw != ADMIN_PASSWORD:
        return web.Response(status=403, text="Unauthorized")

    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_conn():
        print("PC state:", pc.connectionState)
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await pc.close()
            pcs.discard(pc)
            pc_senders.pop(pc, None)

    await pc.setRemoteDescription(offer)
    track = relay.subscribe(camera)
    sender = pc.addTrack(track)
    pc_senders[pc] = sender

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})

# ---------- Quality ----------
async def set_quality(request):
    pw = request.headers.get("Authorization", "")
    if pw != ADMIN_PASSWORD:
        return web.Response(status=403, text="Unauthorized")

    try:
        data = await request.json()
        level = str(data.get("level", "")).upper()
        preset = QUALITY_PRESETS[level]
    except Exception:
        return web.Response(status=400, text="Bad level. Use LOW|MEDIUM|HIGH")

    w, h = preset["size"]
    camera.set_target_size(w, h)
    global QUALITY
    QUALITY = level
    print(f"✅ Quality set to {QUALITY} ({w}x{h})")
    return web.json_response({"ok": True, "quality": QUALITY})

# ---------- Bewegung ----------
async def motion_status(request):
    """Sendet True/False, ob Bewegung erkannt wurde."""
    return web.json_response({"motion": bool(camera.motion_detected)})

# ---------- Login ----------
async def login(request):
    data = await request.json()
    if data.get("password") == ADMIN_PASSWORD:
        return web.Response(status=200, text="OK")
    return web.Response(status=403, text="Wrong password")

# ---------- Static ----------
async def index(request):
    return web.FileResponse("templates/index1.html")

async def javascript(request):
    return web.FileResponse("static/js/client1.js")

# ---------- Shutdown ----------
async def on_shutdown(app):
    print("🛑 Server shutting down...")
    camera.stop()
    for pc in pcs:
        await pc.close()
    pcs.clear()
    pc_senders.clear()
    print("📷 Kamera gestoppt & PCs geschlossen.")

# ---------- App ----------
def create_app():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/client1.js", javascript)
    app.router.add_get("/motion", motion_status)
    app.router.add_post("/offer", offer)
    app.router.add_post("/login", login)
    app.router.add_post("/quality", set_quality)
    app.router.add_static("/static/", path="static", name="static")
    app.on_shutdown.append(on_shutdown)
    return app

if __name__ == "__main__":
    web.run_app(create_app(), host="192.168.178.159", port=8080)