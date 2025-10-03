import cv2
from aiortc import VideoStreamTrack
from av import VideoFrame
import numpy as np
import threading

class CameraStream(VideoStreamTrack):
    """Optimierter Kamera-Stream mit Threading für flüssigere FPS."""

    def __init__(self, camera_index=0):
        super().__init__()
        self.cap = cv2.VideoCapture(camera_index)

        if not self.cap.isOpened():
            print(f"❌ Kamera mit Index {camera_index} konnte nicht geöffnet werden!")
            self.frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        else:
            # Kamera-Parameter
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # Optional: Automatik deaktivieren (nicht jede Cam unterstützt das)
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # 0.25 = Manuell
            self.cap.set(cv2.CAP_PROP_EXPOSURE, 0)        # Anpassen für Helligkeit
            self.cap.set(cv2.CAP_PROP_AUTO_WB, 0)          # Auto White Balance aus

        self.frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.running = True

        # Extra Thread starten
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self):
        """Separater Thread, liest immer das neueste Frame."""
        while self.running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                # Immer nur das letzte Frame speichern
                self.frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        frame = VideoFrame.from_ndarray(self.frame, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame

    def stop(self):
        self.running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()
            print("📷 Kamera gestoppt")

    def __del__(self):
        self.stop()
        print("📷 Kamera freigegeben (Destructor)")