"""
macmini/test_server.py — unit tests for the brain + app API.

Run on the Mac with the deployment venv (no pytest needed):
    ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server -v
Supabase and Ollama are mocked; nothing here touches the network.
"""

import time
import unittest
from unittest import mock

from macmini import server

# 1x1 white pixel JPEG — smallest realistic valid frame body.
TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300ffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffc00b080001000101011100ffc40014000100000000000"
    "00000000000000000000009ffc40014100100000000000000000000000000000000ffda"
    "0008010100003f0037ffd9"
)


class ApiTest(unittest.TestCase):
    def setUp(self):
        server._frames.clear()
        self.client = server.app.test_client()

    # --- existing Phase 1 contract (must never break) ---

    def test_health_contract(self):
        body = self.client.get("/").get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "leofric-brain")
        self.assertEqual(body["model"], server.MODEL)

    def test_chat_requires_message(self):
        resp = self.client.post("/chat", json={})
        self.assertEqual(resp.status_code, 400)

    # --- ingest + nodes + feed ---

    def test_ingest_rejects_non_jpeg(self):
        resp = self.client.post("/ingest/frame/leofric", data=b"not a jpeg")
        self.assertEqual(resp.status_code, 400)

    def test_ingest_then_node_online(self):
        resp = self.client.post(
            "/ingest/frame/leofric",
            data=TINY_JPEG,
            content_type="image/jpeg",
        )
        self.assertEqual(resp.status_code, 200)
        with mock.patch.object(server, "_supabase_last_event_times", return_value={}):
            nodes = self.client.get("/nodes").get_json()["nodes"]
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["name"], "leofric")
        self.assertTrue(nodes[0]["online"])
        self.assertTrue(nodes[0]["streaming"])

    def test_stale_node_reports_offline(self):
        server._frames["leofric"] = {
            "jpeg": TINY_JPEG,
            "at": time.time() - server.NODE_ONLINE_WINDOW_SECONDS - 5,
        }
        with mock.patch.object(server, "_supabase_last_event_times", return_value={}):
            nodes = self.client.get("/nodes").get_json()["nodes"]
        self.assertFalse(nodes[0]["online"])

    def test_feed_without_frames_is_503(self):
        resp = self.client.get("/feed")
        self.assertEqual(resp.status_code, 503)

    def test_feed_streams_multipart_jpeg(self):
        self.client.post(
            "/ingest/frame/leofric", data=TINY_JPEG, content_type="image/jpeg"
        )
        resp = self.client.get("/feed")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("multipart/x-mixed-replace", resp.content_type)
        first_part = next(resp.response)  # one yielded frame, then hang up
        self.assertIn(b"--leofricframe", first_part)
        self.assertIn(b"Content-Type: image/jpeg", first_part)
        self.assertIn(TINY_JPEG, first_part)
        resp.response.close()

    # --- Supabase-backed endpoints (requests mocked) ---

    def _mock_supabase(self, rows):
        resp = mock.Mock()
        resp.json.return_value = rows
        resp.raise_for_status.return_value = None
        return mock.patch.object(server.requests, "get", return_value=resp)

    def test_events_shape_and_params(self):
        rows = [{"id": 1, "event_type": "person", "node_id": "leofric"}]
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             self._mock_supabase(rows) as get:
            body = self.client.get("/events?limit=999&event_type=person").get_json()
        self.assertEqual(body["events"], rows)
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["limit"], 200)  # clamped from 999
        self.assertEqual(params["event_type"], "eq.person")
        self.assertEqual(params["order"], "created_at.desc")

    def test_conversations_shape(self):
        rows = [{"id": 1, "role": "user", "content": "hi"}]
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             self._mock_supabase(rows):
            body = self.client.get("/conversations").get_json()
        self.assertEqual(body["conversations"], rows)

    def test_history_unconfigured_is_503(self):
        with mock.patch.object(server, "SUPABASE_URL", ""), \
             mock.patch.object(server, "SUPABASE_KEY", ""):
            resp = self.client.get("/events")
        self.assertEqual(resp.status_code, 503)

    def test_history_supabase_failure_is_502(self):
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             mock.patch.object(server.requests, "get", side_effect=OSError("down")):
            resp = self.client.get("/events")
        self.assertEqual(resp.status_code, 502)


if __name__ == "__main__":
    unittest.main()
