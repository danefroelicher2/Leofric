"""
vision/streamer.py — pushes live camera frames to the Mac Mini (Phase 2A).

The iOS app watches the camera through the Mac (GET /feed), not the Pi: the Pi
keeps a single upstream connection instead of serving N viewers, and the app has
one host to talk to. This worker shares the VisionWorker's Camera (a USB camera
can't be opened twice), JPEG-encodes the latest frame a few times a second, and
POSTs it to the brain's /ingest/frame/<node> endpoint.

Streaming is best-effort by design: if the Mac is down or the WiFi blips, we log
the state change once (not a line per failure) and keep retrying quietly. The
vision pipeline never depends on this thread.
"""

import logging
import threading
import time

import cv2
import requests

import config

logger = logging.getLogger(__name__)


class FrameStreamer(threading.Thread):
    """Encode the shared camera's latest frame and push it to the Mac."""

    FAILURE_RETRY_SECONDS = 5.0

    def __init__(self, camera, stop_event):
        super().__init__(name="streamer", daemon=True)
        self.camera = camera
        self.stop_event = stop_event
        self.url = f"{config.MAC_MINI_URL}/ingest/frame/{config.NODE_ID}"
        self.interval = 1.0 / config.STREAM_FPS
        self.encode_params = [
            int(cv2.IMWRITE_JPEG_QUALITY),
            config.STREAM_JPEG_QUALITY,
        ]

    def run(self):
        logger.info("Streamer online -> %s (%.1f fps)", self.url, config.STREAM_FPS)
        connected = None  # tri-state so the first success/failure both log once
        session = requests.Session()  # reuse one TCP connection between frames
        while not self.stop_event.is_set():
            started = time.time()
            frame = self.camera.read()
            if frame is None:  # camera not started yet, or between frames
                time.sleep(0.1)
                continue
            ok, jpeg = cv2.imencode(".jpg", frame, self.encode_params)
            if not ok:
                time.sleep(self.interval)
                continue
            try:
                resp = session.post(
                    self.url,
                    data=jpeg.tobytes(),
                    headers={
                        "Content-Type": "image/jpeg",
                        "X-Node-Role": config.NODE_ROLE,
                    },
                    timeout=5,
                )
                resp.raise_for_status()
                if connected is not True:
                    connected = True
                    logger.info("Streaming to the Mac.")
            except Exception as e:
                if connected is not False:
                    connected = False
                    logger.warning("Streaming paused (Mac unreachable): %s", e)
                time.sleep(self.FAILURE_RETRY_SECONDS)
                continue
            # Hold the target rate regardless of how long encode+POST took.
            elapsed = time.time() - started
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
        logger.info("Streamer stopped.")
