"""Tests for vision/streamer.py against a real local HTTP server.

The streamer talks plain persistent HTTP (http.client), so these tests spin up
an actual http.server on a loopback port rather than mocking the transport —
what's being verified is exactly the wire behavior: frames arrive as JPEG
POSTs on a kept-alive connection, and the streamer survives the server dying
and coming back.
"""

import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

import config
from vision.streamer import FrameStreamer


class _FakeCamera:
    """Returns a tiny valid frame; read() never blocks."""

    def __init__(self):
        self.frame = np.zeros((24, 32, 3), dtype=np.uint8)

    def read(self):
        return self.frame.copy()


class _IngestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive, like waitress on the Mac
    received = []  # (path, body, role) tuples, reset per test

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        type(self).received.append(
            (self.path, body, self.headers.get("X-Node-Role"))
        )
        payload = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass  # keep test output clean


class StreamerTest(unittest.TestCase):
    def setUp(self):
        _IngestHandler.received = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _IngestHandler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self._orig_url = config.MAC_MINI_URL
        config.MAC_MINI_URL = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        config.MAC_MINI_URL = self._orig_url
        self.server.shutdown()
        self.server.server_close()

    def _run_streamer_for(self, seconds):
        stop = threading.Event()
        streamer = FrameStreamer(_FakeCamera(), stop)
        streamer.start()
        time.sleep(seconds)
        stop.set()
        streamer.join(timeout=2)

    def test_streams_jpeg_frames_to_ingest_endpoint(self):
        self._run_streamer_for(1.0)
        frames = _IngestHandler.received
        self.assertGreater(len(frames), 3)  # several frames in a second
        path, body, role = frames[0]
        self.assertEqual(path, f"/ingest/frame/{config.NODE_ID}")
        self.assertTrue(body.startswith(b"\xff\xd8"))  # real JPEG bytes
        self.assertEqual(role, config.NODE_ROLE)

    def test_recovers_after_server_restart(self):
        stop = threading.Event()
        streamer = FrameStreamer(_FakeCamera(), stop)
        streamer.FAILURE_RETRY_SECONDS = 0.2  # keep the test fast
        streamer.start()
        time.sleep(0.5)
        before = len(_IngestHandler.received)
        self.assertGreater(before, 0)

        # Kill the server mid-stream, then bring a new one up on the SAME port.
        self.server.shutdown()
        self.server.server_close()
        time.sleep(0.5)
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), _IngestHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

        time.sleep(1.0)
        stop.set()
        streamer.join(timeout=2)
        self.assertGreater(len(_IngestHandler.received), before)


if __name__ == "__main__":
    unittest.main()
