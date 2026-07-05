"""
vision/camera.py — continuous camera capture with thread-safe frame access.

Why a background thread instead of calling read() inline:
OpenCV's VideoCapture.read() blocks until the next frame is ready. If the main
loop called it between heavy steps (motion, person, identity), frames would pile
up in the driver buffer and we'd process stale images with growing latency.
Instead a dedicated thread continuously grabs frames and keeps only the most
recent one. Downstream code always sees the freshest frame and never blocks on
camera I/O. This "grab latest, drop the rest" pattern is standard for real-time
vision pipelines.
"""

import threading
import time

import cv2

import config


class Camera:
    """Owns the camera device and publishes the latest frame to other threads."""

    def __init__(self, device=None, width=None, height=None, fps=None):
        self.device = device if device is not None else config.CAMERA_DEVICE
        self.width = width or config.CAMERA_WIDTH
        self.height = height or config.CAMERA_HEIGHT
        self.fps = fps or config.CAMERA_FPS

        self._capture = None
        self._latest_frame = None
        self._frame_count = 0
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def start(self):
        """Open the device and begin capturing in a background thread."""
        # CAP_V4L2 = the Linux Video4Linux2 backend, correct for a USB webcam.
        self._capture = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        if not self._capture.isOpened():
            raise RuntimeError(f"Could not open camera device {self.device!r}")

        # MJPG lets the BRIO deliver 720p/1080p at full frame rate over USB; the
        # default uncompressed format (YUYV) is bandwidth-limited to low res.
        self._capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._capture.set(cv2.CAP_PROP_FPS, self.fps)
        # Keep only the newest frame in the driver buffer to minimise latency.
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop, name="camera", daemon=True
        )
        self._thread.start()

        # Wait briefly for the first frame so callers don't immediately get None.
        for _ in range(50):  # up to ~5s
            if self.read() is not None:
                return
            time.sleep(0.1)
        raise RuntimeError("Camera opened but produced no frames within 5s")

    def _capture_loop(self):
        """Background loop: grab frames forever, always keep the newest."""
        while self._running:
            ok, frame = self._capture.read()
            if not ok:
                time.sleep(0.01)  # transient hiccup — pause briefly, then retry
                continue
            with self._lock:
                self._latest_frame = frame
                self._frame_count += 1

    def read(self):
        """Return a copy of the most recent frame, or None if none yet.

        We return a copy so a downstream consumer can safely draw on or modify
        the frame without racing the capture thread overwriting it.
        """
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    @property
    def frame_count(self):
        with self._lock:
            return self._frame_count

    def actual_resolution(self):
        """Resolution the driver actually gave us (may differ from requested)."""
        w = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return w, h

    def stop(self):
        """Stop the capture thread and release the device."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._capture is not None:
            self._capture.release()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()
