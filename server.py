import asyncio
import json
import os
import cv2
import numpy as np
import av

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaRelay

pcs = set()
relay = MediaRelay()

ADMIN_PASSWORD = "Hallo123!"

# ---------- Kamera-Stream ----------
class CameraStream(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(
            cv2.CAP_PROP_BUFFERSIZE, 1
        )
        self.cap.set(cv2.CAP_PROP_FPS, 30)

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        if not self.cap.isOpened():
            # Schwarzes Bild zurückgeben, falls Kamera nicht verfügbar
            black = np.zeros((480, 640, 3), dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(black, format="bgr24")
            frame.pts = pts
            frame.time_base = time_base
            return frame

        ret, frame = self.cap.read()
        if not ret:
            # Falls Frame-Grab fehlschlägt → schwarzes Bild
            black = np.zeros((480, 640, 3), dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(black, format="bgr24")
            frame.pts = pts
            frame.time_base = time_base
            return frame

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        av_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")
        av_frame.pts = pts
        av_frame.time_base = time_base
        return av_frame

    def close(self):
        if self.cap.isOpened():
            self.cap.release()


# nur eine Instanz der Kamera erzeugen
camera = CameraStream()


# ---------- Offer ----------
async def offer(request):
    pw = request.headers.get("Authorization", "")
    if pw != ADMIN_PASSWORD:
        return web.Response(status=403, text="Unauthorized")

    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    await pc.setRemoteDescription(offer)

    # Kamera über Relay teilen
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
    print("🛑 Server shutting down...")
    camera.close()  # Kamera schließen
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
    web.run_app(create_app(), host="192.168.178.159", port=8080)