import cv2
from aiortc import VideoStreamTrack
from av import VideoFrame
import numpy as np
import threading
import asyncio
import time


class MotionCameraStream(VideoStreamTrack):
    """🎥 Kamera-Stream mit Bewegungserkennung und Start-Stabilisierung."""

    def __init__(self, camera_index=0, target_size=(1280, 720), sensitivity=40):
        super().__init__()

        self.cap = cv2.VideoCapture(camera_index)
        self.lock = threading.Lock()
        self.prev_gray = None
        self.motion_detected = False
        self.sensitivity = sensitivity
        self.running = True

        # Wenn Kamera nicht offen → schwarzes Dummy-Bild
        if not self.cap.isOpened():
            print(f"❌ Kamera mit Index {camera_index} konnte nicht geöffnet werden!")
            self.frame = np.zeros((target_size[1], target_size[0], 3), dtype=np.uint8)
        else:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_size[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_size[1])
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            print("📷 Kamera geöffnet – warte 5 Sekunden zur Stabilisierung...")

        # Zielgröße
        self._target_w, self._target_h = target_size
        self.frame = np.zeros((target_size[1], target_size[0], 3), dtype=np.uint8)

        # Stabilisierung starten
        self._warmup_done = False
        self._warmup_thread = threading.Thread(target=self._warmup_camera, daemon=True)
        self._warmup_thread.start()

        # Haupt-Reader-Thread starten
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    # ==============================================
    # 🧊 Kamera-Stabilisierung
    # ==============================================
    def _warmup_camera(self):
        """Wartet, bis die Kamera stabil läuft (z. B. Auto-Exposure, Fokus)."""
        t0 = time.time()
        while time.time() - t0 < 5:  # 5 Sekunden Warmlauf
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self.frame = frame
        self._warmup_done = True
        print("✅ Kamera stabilisiert – Stream freigegeben.")

    # ==============================================
    # 🔄 Kontinuierliches Lesen
    # ==============================================
    def _reader(self):
        while self.running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                continue

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            tw, th = self.get_target_size()
            if (frame.shape[1], frame.shape[0]) != (tw, th):
                frame = cv2.resize(frame, (tw, th), interpolation=cv2.INTER_AREA)

            self.frame = frame
            self._detect_motion(frame)

    # ==============================================
    # 📏 Zielgröße ändern
    # ==============================================
    def set_target_size(self, width: int, height: int):
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
    # 📡 Frame liefern (für WebRTC)
    # ==============================================
    async def recv(self):
        """Gibt Frames an WebRTC aus, erst nach Stabilisierung."""
        while not self._warmup_done:
            await asyncio.sleep(0.05)  # Warten bis Kamera stabilisiert ist

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
        if self.cap and self.cap.isOpened():
            self.cap.release()
            print("📷 Kamera gestoppt")