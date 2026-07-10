# Phase 2B — Security Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Mac learns about person/identity events within a second of detection and keeps a snapshot photo per event; conversations gain session threads; nodes gain roles.

**Architecture:** The Pi already streams frames to the Mac (`vision/streamer.py`). This plan adds a second, event-shaped channel: `brain/maclink.py` POSTs each vision event to the Mac's new `POST /ingest/event/<node>`; the Mac captures the latest in-memory frame as a JPEG snapshot on disk, returns a `snapshot_id`, and the Pi stores that id inside the event's Supabase `metadata`, linking cloud history to Mac-hosted photos (`GET /snapshot/<id>`). Wake-word conversations get a rotating `session_id` (idle gap = new thread). Node roles ride an HTTP header on the existing frame stream.

**Tech Stack:** Flask + requests (Mac, venv at `~/leofric-brain/venv` — flask/requests only), Python 3.13 on the Pi (systemd `leofric.service`), Supabase (existing `events`/`conversations` tables — no schema change needed), `unittest` for tests.

## Global Constraints

- Do NOT change existing route JSON shapes: `GET /`, `POST /chat`, `GET /events`, `GET /conversations`, `GET /feed`, `POST /ingest/frame/<node>` (additive fields to `/nodes` are allowed).
- The Mac's deployed venv gets NO new packages. Pi-side unit tests that touch `config` must stub it via `sys.modules` (config imports python-dotenv, absent on the Mac).
- Event/snapshot flow is best-effort on the Pi: a dead Mac must never stall or crash the vision loop (short timeouts, catch-all, state-change logging — same pattern as `vision/streamer.py`).
- Snapshots live on the Mac only (`~/leofric-brain/snapshots/`), never in the repo; prune oldest beyond `SNAPSHOT_KEEP` (default 2000).
- Repo workflow: develop on the Mac at `/Users/danefroelicher/Leofric`, commit + push, then `git pull` on the Pi (`dane@leofric.local`, key auth, passwordless sudo) and restart `leofric.service`.
- Mac deployment: `cp macmini/server.py ~/leofric-brain/server.py`, then `kill $(lsof -tiTCP:5000 -sTCP:LISTEN)` — launchd (`com.leofric.brain`, KeepAlive) restarts it in ~2s.
- Run Mac tests with: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server -v`

---

### Task 1: Mac — event ingest, snapshot store, snapshot serving, pruning

**Files:**
- Modify: `macmini/server.py` (add after the `/feed` route, before the `/nodes` route)
- Test: `macmini/test_server.py` (append to `ApiTest`, plus new imports and `setUp` lines)

**Interfaces:**
- Produces: `POST /ingest/event/<node>` body `{"event_type": str, "metadata": obj}` → `200 {"ok": true, "snapshot_id": str|null}` (`snapshot_id` non-null only for `person`/`identity` events with a fresh frame). `GET /snapshot/<snapshot_id>` → `image/jpeg` or 404. Module vars `SNAPSHOT_DIR: str`, `SNAPSHOT_KEEP: int`, `SNAPSHOT_EVENT_TYPES: set`, `_NODE_RE: re.Pattern` (tests monkeypatch `SNAPSHOT_DIR`/`SNAPSHOT_KEEP`).
- Consumes: `_frames` / `_latest_frame(node)` and `NODE_ONLINE_WINDOW_SECONDS` already in `server.py`.

- [ ] **Step 1: Write the failing tests** — append to `macmini/test_server.py` inside `ApiTest`, and extend the imports/`setUp`:

At the top of the file, extend the import block:

```python
import os
import shutil
import tempfile
```

In `setUp`, after `server._frames.clear()`:

```python
        self._snapdir = tempfile.mkdtemp(prefix="leofric-snaps-")
        self._old_snapdir = server.SNAPSHOT_DIR
        server.SNAPSHOT_DIR = self._snapdir

    def tearDown(self):
        server.SNAPSHOT_DIR = self._old_snapdir
        shutil.rmtree(self._snapdir, ignore_errors=True)
```

New test methods:

```python
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
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server -v`
Expected: the 6 new tests FAIL with 404s (`/ingest/event` route not defined) or `AttributeError: module ... has no attribute 'SNAPSHOT_DIR'`; the existing 11 still pass.

- [ ] **Step 3: Implement in `macmini/server.py`**

Add `re` to the imports (`import re` after `import os`). Add module config near `NODE_ONLINE_WINDOW_SECONDS`:

```python
# Snapshots: one JPEG per person/identity event, saved on disk so the app's
# Alerts timeline has photos. Pruned oldest-first beyond SNAPSHOT_KEEP.
SNAPSHOT_DIR = os.getenv(
    "LEOFRIC_SNAPSHOT_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots"),
)
SNAPSHOT_KEEP = int(os.getenv("LEOFRIC_SNAPSHOT_KEEP", "2000"))
SNAPSHOT_EVENT_TYPES = {"person", "identity"}  # motion is logged, never photographed
_NODE_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_SNAPSHOT_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,80}")
```

Add the routes after `feed()` (uses existing `_latest_frame` and `NODE_ONLINE_WINDOW_SECONDS`; add `send_file` to the flask import):

```python
def _prune_snapshots():
    files = sorted(
        (
            os.path.join(SNAPSHOT_DIR, name)
            for name in os.listdir(SNAPSHOT_DIR)
            if name.endswith(".jpg")
        ),
        key=os.path.getmtime,
    )
    for path in files[: max(0, len(files) - SNAPSHOT_KEEP)]:
        try:
            os.remove(path)
        except OSError:
            pass


@app.post("/ingest/event/<node>")
def ingest_event(node):
    """Pi pushes a detection event; a fresh frame becomes its snapshot photo."""
    if not _NODE_RE.fullmatch(node):
        return jsonify(error="invalid node name"), 400
    data = request.get_json(force=True, silent=True) or {}
    event_type = (data.get("event_type") or "").strip()
    if not event_type:
        return jsonify(error="missing 'event_type'"), 400
    snapshot_id = None
    if event_type in SNAPSHOT_EVENT_TYPES:
        jpeg, at = _latest_frame(node)
        if jpeg is not None and time.time() - at <= NODE_ONLINE_WINDOW_SECONDS:
            snapshot_id = f"{node}-{int(time.time() * 1000)}"
            os.makedirs(SNAPSHOT_DIR, exist_ok=True)
            with open(os.path.join(SNAPSHOT_DIR, snapshot_id + ".jpg"), "wb") as f:
                f.write(jpeg)
            _prune_snapshots()
    return jsonify(ok=True, snapshot_id=snapshot_id)


@app.get("/snapshot/<snapshot_id>")
def snapshot(snapshot_id):
    if not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        return jsonify(error="not found"), 404
    path = os.path.join(SNAPSHOT_DIR, snapshot_id + ".jpg")
    if not os.path.exists(path):
        return jsonify(error="not found"), 404
    return send_file(path, mimetype="image/jpeg")
```

- [ ] **Step 4: Run the full suite; all pass**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server -v`
Expected: 17 tests, `OK`.

- [ ] **Step 5: Commit**

```bash
git add macmini/server.py macmini/test_server.py
git commit -m "brain: event ingest + per-event snapshot store with pruning"
```

---

### Task 2: Mac — node roles surfaced in /nodes

**Files:**
- Modify: `macmini/server.py` (`ingest_frame()` and `nodes()`)
- Test: `macmini/test_server.py` (append to `ApiTest`)

**Interfaces:**
- Consumes: `X-Node-Role` request header on `POST /ingest/frame/<node>` (Task 4 makes the Pi send it).
- Produces: each entry in `GET /nodes` gains `"role": str|null` (`"security"` / `"assistant"` / null when unknown).

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server -v`
Expected: both new tests FAIL with `KeyError: 'role'`.

- [ ] **Step 3: Implement**

In `ingest_frame()`, replace the `_frames[node] = ...` line:

```python
    role = request.headers.get("X-Node-Role") or None
    with _frames_lock:
        _frames[node] = {"jpeg": jpeg, "at": time.time(), "role": role}
```

In `nodes()`, capture roles alongside times and add the field. Replace the `seen = ...` line and the `result` comprehension:

```python
    with _frames_lock:
        seen = {n: e["at"] for n, e in _frames.items()}
        roles = {n: e.get("role") for n, e in _frames.items()}
    for node_id, at in _supabase_last_event_times().items():
        if at > seen.get(node_id, 0.0):
            seen[node_id] = at
    result = [
        {
            "name": n,
            "online": now - at <= NODE_ONLINE_WINDOW_SECONDS,
            "last_seen": _iso(at),
            "streaming": n in _frames,
            "role": roles.get(n),
        }
        for n, at in sorted(seen.items())
    ]
```

- [ ] **Step 4: Run the full suite; all pass**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server -v`
Expected: 19 tests, `OK`.

- [ ] **Step 5: Commit**

```bash
git add macmini/server.py macmini/test_server.py
git commit -m "brain: per-node role from X-Node-Role frame header, surfaced in /nodes"
```

---

### Task 3: Mac — deploy and verify live

**Files:**
- None created; deploys `macmini/server.py` to `~/leofric-brain/server.py`.

**Interfaces:**
- Consumes: Tasks 1–2 merged into `macmini/server.py`.
- Produces: the live Mac API serves `/ingest/event`, `/snapshot`, role-aware `/nodes`.

- [ ] **Step 1: Deploy (copy must be identical — the MACDOCS drift check depends on it)**

```bash
cp /Users/danefroelicher/Leofric/macmini/server.py ~/leofric-brain/server.py
diff ~/leofric-brain/server.py /Users/danefroelicher/Leofric/macmini/server.py && echo IDENTICAL
kill $(lsof -tiTCP:5000 -sTCP:LISTEN)
sleep 4
curl -s http://localhost:5000/
```
Expected: `IDENTICAL`, then `{"model":"llama3.2","service":"leofric-brain","status":"ok"}`.

- [ ] **Step 2: Verify live against the real Pi frame stream** (the Pi streams 24/7, so a fresh frame exists)

```bash
curl -s -X POST http://localhost:5000/ingest/event/leofric \
  -H 'Content-Type: application/json' \
  -d '{"event_type":"person","metadata":{"count":1}}'
```
Expected: `{"ok":true,"snapshot_id":"leofric-17…"}` (non-null id).

```bash
curl -s -o /tmp/snap-test.jpg -w '%{http_code} %{content_type}\n' \
  http://localhost:5000/snapshot/<snapshot_id-from-above>
ls -la ~/leofric-brain/snapshots/
```
Expected: `200 image/jpeg`, and the snapshots dir contains `<id>.jpg` (~50–150 KB).

- [ ] **Step 3: Push** (Tasks 1–2 are already committed; the deploy itself changes no repo files)

```bash
git push
```

---

### Task 4: Pi — config additions + streamer role header

**Files:**
- Modify: `config.py` (after the STREAM_* block)
- Modify: `vision/streamer.py` (headers in the POST)

**Interfaces:**
- Produces: `config.NODE_ROLE: str` (default `"security"`), `config.SESSION_IDLE_SECONDS: float` (default `180`). Streamer sends `X-Node-Role` on every frame POST (consumed by Task 2's server code).

- [ ] **Step 1: Add config settings** — in `config.py`, directly under the `STREAM_JPEG_QUALITY` line:

```python
# Node role shapes app behavior: a "security" node is camera-first (person
# notifications on); an "assistant" node is mic-first (no notifications).
NODE_ROLE = os.getenv("NODE_ROLE", "security")

# --- Conversation sessions ---
# A pause longer than this between wake-word exchanges starts a new session
# (= a new chat thread in the app) with fresh short-term context.
SESSION_IDLE_SECONDS = float(os.getenv("SESSION_IDLE_SECONDS", "180"))
```

- [ ] **Step 2: Send the role with every frame** — in `vision/streamer.py`, replace the `headers=` line inside `session.post(...)`:

```python
                    headers={
                        "Content-Type": "image/jpeg",
                        "X-Node-Role": config.NODE_ROLE,
                    },
```

- [ ] **Step 3: Syntax check**

Run: `cd /Users/danefroelicher/Leofric && python3 -c "import ast; [ast.parse(open(f).read(), f) for f in ('config.py','vision/streamer.py')]; print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add config.py vision/streamer.py
git commit -m "pi: node role config sent with frame stream; session idle setting"
```

---

### Task 5: Pi — brain/maclink.py event push client

**Files:**
- Create: `brain/maclink.py`
- Create: `tests/__init__.py` (empty)
- Test: `tests/test_maclink.py`

**Interfaces:**
- Produces: `MacLink(base_url=None, node_id=None, timeout=3)` with `send_event(event_type: str, metadata: dict|None) -> str|None` (snapshot_id or None; never raises). Consumed by Task 6.
- Consumes: Task 1's `POST /ingest/event/<node>` contract; `config.MAC_MINI_URL`, `config.NODE_ID`.

- [ ] **Step 1: Write the failing test** — `tests/test_maclink.py`. `config` imports python-dotenv (absent in the Mac venv), so stub it **before** importing the module under test:

```python
"""Unit tests for brain/maclink.py — run on the Mac with the brain venv:
    ~/leofric-brain/venv/bin/python3 -m unittest tests.test_maclink -v
"""

import sys
import unittest
from unittest import mock

sys.modules.setdefault(
    "config",
    mock.Mock(MAC_MINI_URL="http://mac.test:5000", NODE_ID="leofric"),
)

from brain.maclink import MacLink  # noqa: E402


class MacLinkTest(unittest.TestCase):
    def _link(self):
        return MacLink(base_url="http://mac.test:5000", node_id="leofric")

    def test_send_event_returns_snapshot_id(self):
        link = self._link()
        resp = mock.Mock()
        resp.json.return_value = {"ok": True, "snapshot_id": "leofric-123"}
        resp.raise_for_status.return_value = None
        with mock.patch.object(link._session, "post", return_value=resp) as post:
            result = link.send_event("person", {"count": 1})
        self.assertEqual(result, "leofric-123")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "http://mac.test:5000/ingest/event/leofric")
        self.assertEqual(
            kwargs["json"], {"event_type": "person", "metadata": {"count": 1}}
        )

    def test_send_event_null_snapshot(self):
        link = self._link()
        resp = mock.Mock()
        resp.json.return_value = {"ok": True, "snapshot_id": None}
        resp.raise_for_status.return_value = None
        with mock.patch.object(link._session, "post", return_value=resp):
            self.assertIsNone(link.send_event("motion", {}))

    def test_send_event_swallows_network_errors(self):
        link = self._link()
        with mock.patch.object(link._session, "post", side_effect=OSError("down")):
            self.assertIsNone(link.send_event("person", {"count": 1}))  # no raise


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest tests.test_maclink -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'brain.maclink'`.

- [ ] **Step 3: Implement** — `brain/maclink.py`:

```python
"""
brain/maclink.py — best-effort event push from the Pi to the Mac (Phase 2B).

Events already flow to Supabase for durable history (storage/events.py). This
second channel exists for *speed*: the Mac hears about a person at the door in
under a second — soon the trigger for push notifications — and photographs the
moment by pairing the event with the freshest frame it already holds, returning
a snapshot_id the caller stores in the event's Supabase metadata.

Same resilience contract as vision/streamer.py: if the Mac is down, log the
state change once and carry on. The vision loop never depends on this call.
"""

import logging

import requests

import config

logger = logging.getLogger(__name__)


class MacLink:
    def __init__(self, base_url=None, node_id=None, timeout=3):
        base = (base_url or config.MAC_MINI_URL).rstrip("/")
        node = node_id or config.NODE_ID
        self.url = f"{base}/ingest/event/{node}"
        self.timeout = timeout
        self._session = requests.Session()
        self._connected = None  # tri-state so first success/failure both log once

    def send_event(self, event_type, metadata=None):
        """POST one event; return the Mac's snapshot_id (or None). Never raises."""
        try:
            resp = self._session.post(
                self.url,
                json={"event_type": event_type, "metadata": metadata or {}},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            if self._connected is not True:
                self._connected = True
                logger.info("Event link to the Mac is up.")
            return resp.json().get("snapshot_id")
        except Exception as e:
            if self._connected is not False:
                self._connected = False
                logger.warning("Event link to the Mac is down: %s", e)
            return None
```

- [ ] **Step 4: Run to verify pass**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest tests.test_maclink -v`
Expected: 3 tests, `OK`.

- [ ] **Step 5: Commit**

```bash
git add brain/maclink.py tests/__init__.py tests/test_maclink.py
git commit -m "pi: MacLink — best-effort event push to the Mac with snapshot_id return"
```

---

### Task 6: Pi — route vision events through MacLink

**Files:**
- Modify: `main.py` (`VisionWorker.__init__`, the three `self.store.log_event(...)` call sites, plus a new `_log_event` helper)

**Interfaces:**
- Consumes: `MacLink.send_event(event_type, metadata) -> str|None` (Task 5).
- Produces: every vision event reaches the Mac first; when a snapshot was taken its id lands in the Supabase row's `metadata["snapshot_id"]` (the app's Alerts thumbnails, Phase 2D, key off this).

- [ ] **Step 1: Add the import** — in `main.py` after `from brain.client import BrainClient, BrainError`:

```python
from brain.maclink import MacLink
```

- [ ] **Step 2: Construct and use it** — in `VisionWorker.__init__`, after `self.identity = IdentityRecognizer()`:

```python
        self.maclink = MacLink()
```

Add a method to `VisionWorker` (after `__init__`, before `run`):

```python
    def _log_event(self, event_type, metadata):
        """Fast path to the Mac (returns snapshot_id if it photographed the
        moment), then the durable path to Supabase with that id attached."""
        snapshot_id = self.maclink.send_event(event_type, metadata)
        if snapshot_id:
            metadata = dict(metadata, snapshot_id=snapshot_id)
        self.store.log_event(event_type, metadata)
```

Replace the three call sites in `run()`:
- `self.store.log_event("motion", {"area": m.total_area})` → `self._log_event("motion", {"area": m.total_area})`
- `self.store.log_event("person", {"count": len(p.boxes)})` → `self._log_event("person", {"count": len(p.boxes)})`
- the identity one →

```python
                                self._log_event(
                                    "identity",
                                    {"name": f.name, "similarity": round(f.similarity, 3)},
                                )
```

- [ ] **Step 3: Syntax check**

Run: `cd /Users/danefroelicher/Leofric && python3 -c "import ast; ast.parse(open('main.py').read(), 'main.py'); print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "pi: vision events push to the Mac first; snapshot_id stored in Supabase metadata"
```

---

### Task 7: Pi — conversation sessions (one wake-word session = one thread)

**Files:**
- Modify: `brain/conversation.py`
- Modify: `main.py` (`AudioWorker.__init__` and `run`)
- Test: `tests/test_conversation.py`

**Interfaces:**
- Produces: `Conversation(max_turns=12, node_id="leofric", idle_seconds=180)` gains `begin_exchange(now=None) -> str` — returns the current `session_id` (format `"{node_id}-{unix_seconds}"`), rotating to a fresh id **and clearing context** after an idle gap. Existing `add/history/clear` unchanged.
- Consumes: `config.NODE_ID`, `config.SESSION_IDLE_SECONDS` (Task 4); `EventStore.log_conversation(role, content, session_id=...)` already accepts session_id.

- [ ] **Step 1: Write the failing test** — `tests/test_conversation.py` (pure stdlib; no config import needed):

```python
"""Unit tests for brain/conversation.py session rotation:
    ~/leofric-brain/venv/bin/python3 -m unittest tests.test_conversation -v
"""

import unittest

from brain.conversation import Conversation


class SessionTest(unittest.TestCase):
    def test_same_session_within_idle_window(self):
        convo = Conversation(node_id="leofric", idle_seconds=180)
        first = convo.begin_exchange(now=1000.0)
        second = convo.begin_exchange(now=1100.0)  # 100s later — same session
        self.assertEqual(first, second)
        self.assertEqual(first, "leofric-1000")

    def test_idle_gap_rotates_session_and_clears_context(self):
        convo = Conversation(node_id="leofric", idle_seconds=180)
        convo.begin_exchange(now=1000.0)
        convo.add("user", "hello")
        rotated = convo.begin_exchange(now=1300.0)  # 300s later — new session
        self.assertEqual(rotated, "leofric-1300")
        self.assertEqual(convo.history(), [])

    def test_history_survives_within_a_session(self):
        convo = Conversation(node_id="leofric", idle_seconds=180)
        convo.begin_exchange(now=1000.0)
        convo.add("user", "hello")
        convo.begin_exchange(now=1050.0)
        self.assertEqual(len(convo.history()), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest tests.test_conversation -v`
Expected: ERROR — `TypeError: __init__() got an unexpected keyword argument 'node_id'`.

- [ ] **Step 3: Implement** — replace `brain/conversation.py`'s class (keep the module docstring, add a sessions sentence to it):

```python
import time


class Conversation:
    def __init__(self, max_turns=12, node_id="leofric", idle_seconds=180):
        self.max_turns = max_turns
        self.node_id = node_id
        self.idle_seconds = idle_seconds
        self._turns = []  # list of {"role": "user"|"assistant", "content": str}
        self._session_id = None
        self._last_at = 0.0

    def begin_exchange(self, now=None):
        """Call at the start of each user utterance. A pause longer than
        idle_seconds means a new conversation: fresh session id (= a new chat
        thread in the app) and cleared short-term context."""
        now = time.time() if now is None else now
        if self._session_id is None or now - self._last_at > self.idle_seconds:
            self._session_id = f"{self.node_id}-{int(now)}"
            self._turns = []
        self._last_at = now
        return self._session_id

    def add(self, role, content):
        self._turns.append({"role": role, "content": content})
        if len(self._turns) > self.max_turns:
            self._turns = self._turns[-self.max_turns :]

    def history(self):
        return list(self._turns)

    def clear(self):
        self._turns = []
```

- [ ] **Step 4: Wire into `main.py`** — in `AudioWorker.__init__`, replace `self.convo = Conversation()`:

```python
        self.convo = Conversation(
            node_id=config.NODE_ID, idle_seconds=config.SESSION_IDLE_SECONDS
        )
```

In `AudioWorker.run()`, after `logger.info("heard: %s", text)` replace the four store/convo lines so both rows carry the session:

```python
                session_id = self.convo.begin_exchange()
                self.convo.add("user", text)
                self.store.log_conversation("user", text, session_id=session_id)
                try:
                    reply = self.brain.chat(text, history=self.convo.history())
                except BrainError as e:
                    logger.warning("brain unreachable: %s", e)
                    continue
                self.convo.add("assistant", reply)
                self.store.log_conversation("leofric", reply, session_id=session_id)
```

- [ ] **Step 5: Run all Pi-side tests + syntax check**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest tests.test_conversation tests.test_maclink -v && python3 -c "import ast; ast.parse(open('main.py').read(), 'main.py'); print('OK')"`
Expected: 6 tests `OK`, then `OK`.

- [ ] **Step 6: Commit**

```bash
git add brain/conversation.py main.py tests/test_conversation.py
git commit -m "pi: wake-word sessions — idle gap rotates session_id and clears context"
```

---

### Task 8: Deploy to the Pi, verify end-to-end on hardware, close out docs

**Files:**
- Modify: `docs/ROADMAP.md` (Phase 2B checkboxes)

**Interfaces:**
- Consumes: everything above, pushed to `main`.

- [ ] **Step 1: Push, then pull + restart on the Pi**

```bash
git push
ssh dane@leofric.local "cd ~/leofric && git pull --ff-only && sudo systemctl restart leofric && sleep 12 && systemctl is-active leofric && journalctl -u leofric -n 6 --no-pager"
```
Expected: `active`; log shows `Vision online`, `Audio online`, `Streaming to the Mac.` and no tracebacks.

- [ ] **Step 2: Verify the event link came up and events flow** (the camera watches Dane's desk; identity/person events fire within a couple of minutes of someone being in frame)

```bash
ssh dane@leofric.local "journalctl -u leofric --since '-3 min' --no-pager | grep -E 'Event link|person|identity' | tail -5"
ls -lt ~/leofric-brain/snapshots/ | head -4
```
Expected: `Event link to the Mac is up.`, at least one person/identity log line, and fresh `leofric-*.jpg` files on the Mac.

- [ ] **Step 3: Verify the Supabase row carries the snapshot_id and the photo serves**

```bash
curl -s 'http://localhost:5000/events?limit=3&event_type=person' | python3 -m json.tool
```
Expected: newest person event's `metadata` contains `"snapshot_id": "leofric-…"`. Then:

```bash
curl -s -o /tmp/e2e-snap.jpg -w '%{http_code}\n' http://localhost:5000/snapshot/<that-id>
```
Expected: `200`; view `/tmp/e2e-snap.jpg` and confirm it shows the room at the event moment.

- [ ] **Step 4: Verify roles and (with Dane present) a voice session**

```bash
curl -s http://localhost:5000/nodes
```
Expected: `"role":"security"` on the leofric node. **[DANE, optional now — required before 2D]** say "hey Jarvis, what's two plus two", wait for the reply, then:

```bash
curl -s 'http://localhost:5000/conversations?limit=2' | python3 -m json.tool
```
Expected: both rows share a non-null `session_id` like `leofric-17…`.

- [ ] **Step 5: Check off ROADMAP 2B and push**

In `docs/ROADMAP.md`, mark the four 2B checkboxes `[x]` and append a completion line following the 2A pattern (state what was verified on hardware and the date).

```bash
git add docs/ROADMAP.md
git commit -m "docs: Phase 2B complete — security backend verified on hardware"
git push
```
