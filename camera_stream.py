import cv2
from aiortc import VideoStreamTrack
from av import VideoFrame

class CameraStream(VideoStreamTrack):
    """Optimierter Kamera-Stream mit niedriger Latenz für WebRTC."""

    def __init__(self, camera_index=0):
        super().__init__()
        self.cap = cv2.VideoCapture(camera_index)

        if not self.cap.isOpened():
            raise RuntimeError(f"Kamera mit Index {camera_index} konnte nicht geöffnet werden")

        # Kamera-Parameter optimieren
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)   # 720p Breite (1280x720)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(cv2.CAP_PROP_FPS, 30)             # 30 fps
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)       # nur 1 Frame puffern

        print("📷 Kamera gestartet (1280x720 @ 30fps, Low-Latency)")

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        # immer den aktuellsten Frame lesen
        ret, frame = self.cap.read()
        if not ret:
            raise RuntimeError("Kamera konnte nicht gelesen werden")

        # Farbraum BGR → RGB (WebRTC erwartet RGB)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Frame ins richtige Format umwandeln
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

    def stop(self):
        """Kamera sauber schließen."""
        if self.cap and self.cap.isOpened():
            self.cap.release()
            print("📷 Kamera gestoppt")

    def __del__(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()
            print("📷 Kamera freigegeben (Destructor)")
