from picamera2 import Picamera2
from aiortc import VideoStreamTrack
from av import VideoFrame
import numpy as np
import threading
import asyncio
import time
import cv2


class MotionCameraStream(VideoStreamTrack):
    """🎥 Kamera-Stream mit Bewegungserkennung und Start-Stabilisierung (Pi5 + Picamera2)."""

    def __init__(self, target_size=(1280, 720), sensitivity=40):
        super().__init__()

        self.lock = threading.Lock()
        self.prev_gray = None
        self.motion_detected = False
        self.sensitivity = sensitivity
        self.running = True

        # Picamera2 initialisieren
        self.picam2 = Picamera2()
        config = self.picam2.create_video_configuration(
            main={"size": target_size, "format": "RGB888"}
        )
        self.picam2.configure(config)

        # Buffer für aktuelles Frame
        self.frame = np.zeros((target_size[1], target_size[0], 3), dtype=np.uint8)

        # Kamera starten
        print("📷 Starte CSI-Kamera…")
        self.picam2.start()

        # Stabilisierung
        self._warmup_done = False
        self._warmup_thread = threading.Thread(target=self._warmup_camera, daemon=True)
        self._warmup_thread.start()

        # Hauptloop
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

        self._target_w, self._target_h = target_size

    # ==============================================
    # 🧊 Kamera-Stabilisierung
    # ==============================================
    def _warmup_camera(self):
        time.sleep(2.5)  # 2–3 Sekunden reichen bei Picamera2
        self._warmup_done = True
        print("✅ Kamera stabilisiert – Stream freigegeben.")

    # ==============================================
    # 🔄 Frames kontinuierlich lesen
    # ==============================================
    def _reader(self):
        while self.running:
            frame = self.picam2.capture_array()
            if frame is None:
                continue

            # Resize, falls Zielgröße geändert wurde
            tw, th = self.get_target_size()
            if (frame.shape[1], frame.shape[0]) != (tw, th):
                frame = cv2.resize(frame, (tw, th), interpolation=cv2.INTER_AREA)

            self.frame = frame
            self._detect_motion(frame)

    # ==============================================
    # 📏 Zielgröße
    # ==============================================
    def set_target_size(self, width, height):
        with self.lock:
            self._target_w, self._target_h = width, height

    def get_target_size(self):
        with self.lock:
            return self._target_w, self._target_h

    # ==============================================
    # 🧠 Bewegungserkennung
    # ==============================================
    def _detect_motion(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if self.prev_gray is None:
            self.prev_gray = gray
            return

        diff = cv2.absdiff(self.prev_gray, gray)
        thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]
        motion_level = np.sum(thresh) / 255
        self.prev_gray = gray
        self.motion_detected = motion_level > self.sensitivity * 1000

    # ==============================================
    # 📡 WebRTC Frame liefern
    # ==============================================
    async def recv(self):
        while not self._warmup_done:
            await asyncio.sleep(0.05)

        pts, time_base = await self.next_timestamp()
        frm = VideoFrame.from_ndarray(self.frame, format="rgb24")
        frm.pts = pts
        frm.time_base = time_base
        return frm

    # ==============================================
    # 🧹 Stoppen
    # ==============================================
    def stop(self):
        self.running = False
        try:
            self.picam2.stop()
        except:
            pass
        print("📷 Kamera gestoppt")

# Hallo