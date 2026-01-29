from aiortc import VideoStreamTrack
from av import VideoFrame
import asyncio
import threading
import time
import os
import numpy as np

from picamera2 import Picamera2)
import cv2


class MotionCameraStream(VideoStreamTrack):
    _cv_configured = False

    def __init__(self, camera_index=0, target_size=(1280, 720), sensitivity=40, max_fps=None, use_all_cores=True):
        super().__init__()

        if use_all_cores and not MotionCameraStream._cv_configured:
            MotionCameraStream._configure_cv_threads()

        self.picam = self._open_camera(camera_index)

        config = self.picam.create_video_configuration(
            main={"size": target_size, "format": "RGB888"},
            controls={"AwbEnable": True, "AeEnable": True}
        )

        self.picam.configure(config)
        self.picam.start()

        self.frame = np.zeros((target_size[1], target_size[0], 3), dtype=np.uint8)

        self.prev_gray = None
        self.motion_detected = False
        self.sensitivity = sensitivity
        self.running = True
        self.max_fps = max_fps

        time.sleep(1.5)  # AWB stabilisieren

        # eigener Frame-Reader
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self):
        frame_interval = None
        next_frame_time = None
        if self.max_fps and self.max_fps > 0:
            frame_interval = 1.0 / self.max_fps
            next_frame_time = time.monotonic()

        while self.running:
            frame = self.picam.capture_array()     # RGB888 Frame

            # Bewegung erkennen
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            if self.prev_gray is not None:
                diff = cv2.absdiff(self.prev_gray, gray)
                thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]
                motion_level = np.sum(thresh) / 255
                self.motion_detected = motion_level > self.sensitivity * 1000

            self.prev_gray = gray
            self.frame = frame
            if frame_interval is not None and next_frame_time is not None:
                next_frame_time += frame_interval
                sleep_for = next_frame_time - time.monotonic()
                if sleep_for > 0:
                    time.sleep(sleep_for)

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        frm = VideoFrame.from_ndarray(self.frame, format="rgb24")
        frm.pts = pts
        frm.time_base = time_base
        return frm

    def stop(self):
        self.running = False
        self.picam.stop()
        print("Kamera gestoppt.")

    @staticmethod
    def _configure_cv_threads():
        cpu_threads = max(1, os.cpu_count() or 1)
        try:
            cv2.setUseOptimized(True)
            cv2.setNumThreads(cpu_threads)
        except Exception:
            pass
        MotionCameraStream._cv_configured = True

    @staticmethod
    def _open_camera(camera_index):
        try:
            return Picamera2(camera_num=camera_index)
        except TypeError:
            try:
                return Picamera2(camera_index)
            except TypeError:
                return Picamera2()
