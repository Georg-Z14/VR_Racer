import cv2
from aiortc import VideoStreamTrack
from av import VideoFrame
import numpy as np

class CameraStream(VideoStreamTrack):
    """Optimierter Kamera-Stream mit Fallback, falls Kamera kein Bild liefert."""

    def __init__(self, camera_index=0):
        super().__init__()
        self.cap = cv2.VideoCapture(camera_index)

        if not self.cap.isOpened():
            print(f"❌ Kamera mit Index {camera_index} konnte nicht geöffnet werden!")
        else:
            # Kamera-Parameter einstellen
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        if not self.cap or not self.cap.isOpened():
            # Fallback: schwarzes Bild
            black = np.zeros((720, 1280, 3), dtype=np.uint8)
            frame = VideoFrame.from_ndarray(black, format="rgb24")
            frame.pts = pts
            frame.time_base = time_base
            return frame

        ret, frame = self.cap.read()
        if not ret:
            # Fallback: schwarzes Bild
            black = np.zeros((720, 1280, 3), dtype=np.uint8)
            frame = VideoFrame.from_ndarray(black, format="rgb24")
            frame.pts = pts
            frame.time_base = time_base
            return frame

        # BGR → RGB
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

    def stop(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()
            print("📷 Kamera gestoppt")

    def __del__(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()
            print("📷 Kamera freigegeben (Destructor)")