import asyncio
import json
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from camera_stream import CameraStream

pcs = set()

# ---- WebRTC Offer ----
async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    # Remote Description vom Browser setzen
    await pc.setRemoteDescription(offer)

    # Kamera-Track hinzufügen (das reicht, kein Transceiver nötig)
    pc.addTrack(CameraStream())

    # Answer erzeugen
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


# ---- Shutdown ----
async def on_shutdown(app):
    for pc in pcs:
        for sender in pc.getSenders():
            track = sender.track
            if track and isinstance(track, CameraStream):
                track.stop()
        await pc.close()
    pcs.clear()

# ---- Static Routes ----
async def index(request):
    return web.FileResponse("index1.html")

async def javascript(request):
    return web.FileResponse("client1.js")

# ---- Main App ----
def create_app():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/client1.js", javascript)
    app.router.add_post("/offer", offer)
    app.on_shutdown.append(on_shutdown)
    app.router.add_static("/static/", path="static", name="static")
    return app


if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="127.0.0.1", port=8080)
