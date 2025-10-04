import json
import asyncio
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from camera_stream import MotionCameraStream as CameraStream

pcs = set()

async def offer(request):
    """Nimmt WebRTC-Angebot vom Browser entgegen und antwortet mit Answer."""
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    # Quelle auswählen: Webcam oder RTSP
    pc.addTrack(CameraStream(0))


    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )

async def on_shutdown(app):
    """Beim Beenden alle Verbindungen schließen."""
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

async def index(request):
    """Standardseite: index1.html ausliefern."""
    return web.FileResponse("templates/index1.html")

async def javascript(request):
    return web.FileResponse("static/js/client1.js")

def create_app():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/client1.js", javascript)
    app.router.add_post("/offer", offer)
    app.on_shutdown.append(on_shutdown)
    return app