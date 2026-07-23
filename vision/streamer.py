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

import http.client
import logging
import threading
import time
from urllib.parse import urlsplit

import cv2

import config

logger = logging.getLogger(__name__)


class FrameStreamer(threading.Thread):
    """Encode the shared camera's latest frame and push it to the Mac.

    Transport is stdlib http.client over one persistent connection, NOT
    requests: at 15fps the sender shares the GIL with the vision and audio
    inference threads, and requests' per-call Python overhead (thousands of
    bytecodes through urllib3) stretched from ~2ms standalone to ~100ms under
    that contention, capping the feed at ~6fps. http.client does the same POST
    in a fraction of the bytecode, and the heavy steps (JPEG encode, socket
    send) release the GIL.
    """

    FAILURE_RETRY_SECONDS = 5.0

    def __init__(self, camera, stop_event):
        super().__init__(name="streamer", daemon=True)
        self.camera = camera
        self.stop_event = stop_event
        self.url = f"{config.MAC_MINI_URL}/ingest/frame/{config.NODE_ID}"
        parts = urlsplit(config.MAC_MINI_URL)
        self.host = parts.hostname
        self.port = parts.port or 80
        self.path = f"/ingest/frame/{config.NODE_ID}"
        self.headers = {
            "Content-Type": "image/jpeg",
            "X-Node-Role": config.NODE_ROLE,
        }
        self.interval = 1.0 / config.STREAM_FPS
        self.encode_params = [
            int(cv2.IMWRITE_JPEG_QUALITY),
            config.STREAM_JPEG_QUALITY,
        ]
        self._conn = None

    def _post_frame(self, body):
        """POST one frame over the persistent connection; raise on any failure."""
        if self._conn is None:
            self._conn = http.client.HTTPConnection(self.host, self.port, timeout=5)
        self._conn.request("POST", self.path, body=body, headers=self.headers)
        resp = self._conn.getresponse()
        resp.read()  # drain so the connection can be reused
        if resp.status != 200:
            raise RuntimeError(f"ingest returned HTTP {resp.status}")

    def _drop_connection(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def run(self):
        logger.info("Streamer online -> %s (%.1f fps)", self.url, config.STREAM_FPS)
        connected = None  # tri-state so the first success/failure both log once
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
                self._post_frame(jpeg.tobytes())
                if connected is not True:
                    connected = True
                    logger.info("Streaming to the Mac.")
            except Exception as e:
                self._drop_connection()
                if connected is not False:
                    connected = False
                    logger.warning("Streaming paused (Mac unreachable): %s", e)
                time.sleep(self.FAILURE_RETRY_SECONDS)
                continue
            # Hold the target rate regardless of how long encode+POST took.
            elapsed = time.time() - started
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
        self._drop_connection()
        logger.info("Streamer stopped.")
