from aiortc import VideoStreamTrack
from av import VideoFrame
import asyncio
import threading
import time
import os
import multiprocessing as mp
from multiprocessing.shared_memory import SharedMemory
from typing import Optional, Tuple
import numpy as np

from picamera2 import Picamera2
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


def _camera_worker(
    shm_name: str,
    width: int,
    height: int,
    camera_index: int,
    max_fps: float,
    use_all_cores: bool,
    pixel_format: str,
    swap_rb: bool,
    buffer_count: int,
    queue: bool,
    lock: mp.Lock,
    stop_event: mp.Event,
):
    if use_all_cores:
        MotionCameraStream._configure_cv_threads()

    picam = MotionCameraStream._open_camera(camera_index)
    controls = {"AwbEnable": True, "AeEnable": True}
    if max_fps and max_fps > 0:
        controls["FrameRate"] = max_fps

    config = picam.create_video_configuration(
        main={"size": (width, height), "format": pixel_format},
        controls=controls,
        buffer_count=buffer_count,
        queue=queue,
    )
    picam.configure(config)
    picam.start()

    shm = SharedMemory(name=shm_name)
    shared_frame = np.ndarray((height, width, 3), dtype=np.uint8, buffer=shm.buf)

    frame_interval = None
    next_frame_time = None
    if max_fps and max_fps > 0:
        frame_interval = 1.0 / max_fps
        next_frame_time = time.monotonic()

    try:
        while not stop_event.is_set():
            frame = picam.capture_array()
            if swap_rb:
                frame = frame[:, :, ::-1].copy()
            if frame.shape[0] != height or frame.shape[1] != width:
                frame = cv2.resize(frame, (width, height))
            with lock:
                np.copyto(shared_frame, frame)

            if frame_interval is not None and next_frame_time is not None:
                next_frame_time += frame_interval
                sleep_for = next_frame_time - time.monotonic()
                if sleep_for > 0:
                    time.sleep(sleep_for)
    finally:
        try:
            picam.stop()
        except Exception:
            pass
        shm.close()


class CameraProcess:
    def __init__(
        self,
        camera_index=0,
        target_size=(1280, 720),
        max_fps=None,
        use_all_cores=True,
        pixel_format: str = "RGB888",
        frame_format: str = "rgb24",
        swap_rb: bool = False,
        buffer_count: int = 2,
        queue: bool = False,
        mp_context: Optional[mp.context.BaseContext] = None,
    ):
        self._width, self._height = target_size
        self._ctx = mp_context or mp.get_context("spawn")
        self._lock = self._ctx.Lock()
        self._stop_event = self._ctx.Event()
        self._shm = SharedMemory(create=True, size=self._width * self._height * 3)
        self._frame_format = frame_format
        self._proc = self._ctx.Process(
            target=_camera_worker,
            args=(
                self._shm.name,
                self._width,
                self._height,
                camera_index,
                max_fps,
                use_all_cores,
                pixel_format,
                swap_rb,
                buffer_count,
                queue,
                self._lock,
                self._stop_event,
            ),
        )
        self._proc.daemon = True
        self._proc.start()

    @property
    def shm_name(self) -> str:
        return self._shm.name

    @property
    def lock(self) -> mp.Lock:
        return self._lock

    @property
    def target_size(self) -> Tuple[int, int]:
        return self._width, self._height

    def create_track(self):
        return SharedMemoryCameraStream(self._shm.name, self.target_size, self._lock, self._frame_format)

    def stop(self):
        self._stop_event.set()
        if self._proc.is_alive():
            self._proc.join(timeout=2.0)
        if self._proc.is_alive():
            self._proc.terminate()
            self._proc.join(timeout=2.0)
        try:
            self._shm.close()
        except Exception:
            pass
        try:
            self._shm.unlink()
        except FileNotFoundError:
            pass


class SharedMemoryCameraStream(VideoStreamTrack):
    def __init__(
        self,
        shm_name: str,
        target_size=(1280, 720),
        lock: Optional[mp.Lock] = None,
        frame_format: str = "rgb24",
    ):
        super().__init__()
        width, height = target_size
        self._shm = SharedMemory(name=shm_name)
        self._lock = lock
        self._frame_format = frame_format
        self._shared_frame = np.ndarray((height, width, 3), dtype=np.uint8, buffer=self._shm.buf)
        self._local_frame = np.zeros((height, width, 3), dtype=np.uint8)

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        if self._lock:
            with self._lock:
                np.copyto(self._local_frame, self._shared_frame)
        else:
            np.copyto(self._local_frame, self._shared_frame)
        frm = VideoFrame.from_ndarray(self._local_frame, format=self._frame_format)
        frm.pts = pts
        frm.time_base = time_base
        return frm

    def stop(self):
        super().stop()
        try:
            self._shm.close()
        except Exception:
            pass
