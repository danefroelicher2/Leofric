"""
macmini/test_server.py — unit tests for the brain + app API.

Run on the Mac with the deployment venv (no pytest needed):
    ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server -v
Supabase and Ollama are mocked; nothing here touches the network.
"""

import os
import shutil
import tempfile
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
        self._snapdir = tempfile.mkdtemp(prefix="leofric-snaps-")
        self._old_snapdir = server.SNAPSHOT_DIR
        server.SNAPSHOT_DIR = self._snapdir

    def tearDown(self):
        server.SNAPSHOT_DIR = self._old_snapdir
        shutil.rmtree(self._snapdir, ignore_errors=True)

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

    def test_ingest_frame_rejects_bad_node(self):
        resp = self.client.post(
            "/ingest/frame/bad..name", data=TINY_JPEG, content_type="image/jpeg"
        )
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

    # --- event ingest + snapshots ---

    def _post_frame(self, node="leofric"):
        return self.client.post(
            f"/ingest/frame/{node}", data=TINY_JPEG, content_type="image/jpeg"
        )

    def test_person_event_with_frame_saves_snapshot(self):
        self._post_frame()
        resp = self.client.post(
            "/ingest/event/leofric",
            json={"event_type": "person", "metadata": {"count": 1}},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["ok"])
        self.assertIsNotNone(body["snapshot_id"])
        path = os.path.join(server.SNAPSHOT_DIR, body["snapshot_id"] + ".jpg")
        self.assertTrue(os.path.exists(path))
        got = self.client.get(f"/snapshot/{body['snapshot_id']}")
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.data, TINY_JPEG)

    def test_event_without_frame_has_no_snapshot(self):
        resp = self.client.post(
            "/ingest/event/leofric", json={"event_type": "person", "metadata": {}}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.get_json()["snapshot_id"])

    def test_motion_event_never_snapshots(self):
        self._post_frame()
        resp = self.client.post(
            "/ingest/event/leofric", json={"event_type": "motion", "metadata": {}}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.get_json()["snapshot_id"])
        self.assertEqual(os.listdir(server.SNAPSHOT_DIR), [])

    def test_event_requires_type_and_valid_node(self):
        self.assertEqual(
            self.client.post("/ingest/event/leofric", json={}).status_code, 400
        )
        self.assertEqual(
            self.client.post(
                "/ingest/event/bad..name", json={"event_type": "person"}
            ).status_code,
            400,
        )

    def test_snapshot_rejects_bad_ids_and_missing(self):
        self.assertEqual(self.client.get("/snapshot/no-such-id").status_code, 404)
        self.assertEqual(self.client.get("/snapshot/..%2Fetc").status_code, 404)

    def test_snapshot_pruning_keeps_newest(self):
        old_keep = server.SNAPSHOT_KEEP
        server.SNAPSHOT_KEEP = 2
        try:
            self._post_frame()
            ids = []
            for _ in range(4):
                body = self.client.post(
                    "/ingest/event/leofric", json={"event_type": "person"}
                ).get_json()
                ids.append(body["snapshot_id"])
                time.sleep(0.02)  # distinct mtimes/ids
            remaining = sorted(os.listdir(server.SNAPSHOT_DIR))
            self.assertEqual(len(remaining), 2)
            self.assertIn(ids[-1] + ".jpg", remaining)
            self.assertNotIn(ids[0] + ".jpg", remaining)
        finally:
            server.SNAPSHOT_KEEP = old_keep

    # --- node roles ---

    def test_node_role_from_frame_header(self):
        self.client.post(
            "/ingest/frame/leofric",
            data=TINY_JPEG,
            content_type="image/jpeg",
            headers={"X-Node-Role": "security"},
        )
        with mock.patch.object(server, "_supabase_last_event_times", return_value={}):
            nodes = self.client.get("/nodes").get_json()["nodes"]
        self.assertEqual(nodes[0]["role"], "security")

    def test_node_role_null_when_never_sent(self):
        self._post_frame()  # no header
        with mock.patch.object(server, "_supabase_last_event_times", return_value={}):
            nodes = self.client.get("/nodes").get_json()["nodes"]
        self.assertIsNone(nodes[0]["role"])

    # --- app-originated chat (Phase 2D) ---

    def _mock_ollama_and_supabase(self, reply="Hello there"):
        """Mocks both requests.post (Ollama /api/chat) and _supabase_post."""
        ollama_resp = mock.Mock()
        ollama_resp.json.return_value = {"message": {"content": reply}}
        ollama_resp.raise_for_status.return_value = None
        return mock.patch.object(server.requests, "post", return_value=ollama_resp)

    def test_app_chat_mints_session_id_when_absent(self):
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             self._mock_ollama_and_supabase() as post, \
             mock.patch.object(server, "_supabase_post") as supa_post:
            resp = self.client.post("/app/chat", json={"message": "hi"})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["response"], "Hello there")
        self.assertTrue(body["session_id"].startswith("app-"))
        self.assertEqual(supa_post.call_count, 2)
        user_row = supa_post.call_args_list[0].args[1]
        leofric_row = supa_post.call_args_list[1].args[1]
        self.assertEqual(user_row["role"], "user")
        self.assertEqual(user_row["content"], "hi")
        self.assertEqual(user_row["node_id"], "app")
        self.assertEqual(user_row["session_id"], body["session_id"])
        self.assertEqual(leofric_row["role"], "leofric")
        self.assertEqual(leofric_row["content"], "Hello there")

    def test_app_chat_reuses_provided_session_id(self):
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             self._mock_ollama_and_supabase(), \
             mock.patch.object(server, "_supabase_post") as supa_post:
            resp = self.client.post(
                "/app/chat", json={"message": "hi", "session_id": "app-123"}
            )
        self.assertEqual(resp.get_json()["session_id"], "app-123")
        self.assertEqual(supa_post.call_args_list[0].args[1]["session_id"], "app-123")

    def test_app_chat_requires_message(self):
        resp = self.client.post("/app/chat", json={})
        self.assertEqual(resp.status_code, 400)

    def test_app_chat_forwards_history_to_ollama(self):
        history = [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "reply"}]
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             self._mock_ollama_and_supabase() as post, \
             mock.patch.object(server, "_supabase_post"):
            self.client.post("/app/chat", json={"message": "hi", "history": history})
        sent_messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(sent_messages[0]["content"], server.SYSTEM_PROMPT)
        self.assertIn({"role": "user", "content": "earlier"}, sent_messages)
        self.assertEqual(sent_messages[-1], {"role": "user", "content": "hi"})

    def test_app_chat_still_returns_reply_if_persistence_fails(self):
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             self._mock_ollama_and_supabase(), \
             mock.patch.object(server, "_supabase_post", side_effect=OSError("down")):
            resp = self.client.post("/app/chat", json={"message": "hi"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["response"], "Hello there")

    def test_app_chat_works_without_supabase_configured(self):
        with mock.patch.object(server, "SUPABASE_URL", ""), \
             mock.patch.object(server, "SUPABASE_KEY", ""), \
             self._mock_ollama_and_supabase():
            resp = self.client.post("/app/chat", json={"message": "hi"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["response"], "Hello there")

    def test_app_chat_ollama_failure_is_502(self):
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             mock.patch.object(server.requests, "post", side_effect=OSError("down")):
            resp = self.client.post("/app/chat", json={"message": "hi"})
        self.assertEqual(resp.status_code, 502)

    def test_supabase_post_sends_row(self):
        resp = mock.Mock()
        resp.raise_for_status.return_value = None
        with mock.patch.object(server, "SUPABASE_URL", "http://sb"), \
             mock.patch.object(server, "SUPABASE_KEY", "key"), \
             mock.patch.object(server.requests, "post", return_value=resp) as post:
            server._supabase_post("conversations", {"role": "user", "content": "hi"})
        args, kwargs = post.call_args
        self.assertEqual(args[0], "http://sb/rest/v1/conversations")
        self.assertEqual(kwargs["json"], {"role": "user", "content": "hi"})
        self.assertEqual(kwargs["headers"]["apikey"], "key")

    # --- device registration (Phase 2E) ---

    def test_register_device_stores_token(self):
        import tempfile, os as _os
        with tempfile.TemporaryDirectory() as d:
            path = _os.path.join(d, "devices.json")
            with mock.patch.object(server, "DEVICES_FILE", path):
                resp = self.client.post("/devices", json={"token": "a1b2c3d4"})
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.get_json()["ok"])
                self.assertEqual(server._load_device_tokens(), ["a1b2c3d4"])

    def test_register_device_dedupes(self):
        import tempfile, os as _os
        with tempfile.TemporaryDirectory() as d:
            path = _os.path.join(d, "devices.json")
            with mock.patch.object(server, "DEVICES_FILE", path):
                self.client.post("/devices", json={"token": "aa"})
                self.client.post("/devices", json={"token": "aa"})
                self.assertEqual(server._load_device_tokens(), ["aa"])

    def test_register_device_rejects_bad_token(self):
        self.assertEqual(self.client.post("/devices", json={}).status_code, 400)
        self.assertEqual(
            self.client.post("/devices", json={"token": "not hex!"}).status_code, 400
        )

    def test_load_device_tokens_missing_file_is_empty(self):
        with mock.patch.object(server, "DEVICES_FILE", "/nonexistent/devices.json"):
            self.assertEqual(server._load_device_tokens(), [])

    # --- push hook in ingest (Phase 2E) ---

    def test_ingest_event_triggers_push_for_identity(self):
        self._post_frame()  # so a snapshot is captured
        sent = []
        fake_apns = mock.Mock()
        fake_apns.send.side_effect = lambda *a, **k: sent.append(a) or True
        with mock.patch.object(server, "_apns", fake_apns), \
             mock.patch.object(server, "_load_device_tokens", return_value=["tok1"]), \
             mock.patch.dict(server._last_notified, clear=True):
            self.client.post(
                "/ingest/event/leofric",
                json={"event_type": "identity", "metadata": {"name": "dane"}},
            )
        self.assertEqual(len(sent), 1)  # one device notified

    def test_ingest_event_motion_does_not_push(self):
        fake_apns = mock.Mock()
        with mock.patch.object(server, "_apns", fake_apns), \
             mock.patch.object(server, "_load_device_tokens", return_value=["tok1"]):
            self.client.post("/ingest/event/leofric", json={"event_type": "motion"})
        fake_apns.send.assert_not_called()

    def test_ingest_event_no_push_when_apns_unconfigured(self):
        with mock.patch.object(server, "_apns", None), \
             mock.patch.object(server, "_load_device_tokens", return_value=["tok1"]):
            resp = self.client.post(
                "/ingest/event/leofric",
                json={"event_type": "identity", "metadata": {"name": "dane"}},
            )
        self.assertEqual(resp.status_code, 200)  # ingest still succeeds

    def test_ingest_event_push_failure_does_not_break_ingest(self):
        fake_apns = mock.Mock()
        fake_apns.send.side_effect = RuntimeError("boom")
        with mock.patch.object(server, "_apns", fake_apns), \
             mock.patch.object(server, "_load_device_tokens", return_value=["tok1"]), \
             mock.patch.dict(server._last_notified, clear=True):
            resp = self.client.post(
                "/ingest/event/leofric",
                json={"event_type": "identity", "metadata": {"name": "unknown"}},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
