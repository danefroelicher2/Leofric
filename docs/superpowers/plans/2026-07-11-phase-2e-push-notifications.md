# Phase 2E — Push Notifications + Remote Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a person is detected at a security node, the Mac sends an identity-aware push notification (with the snapshot photo) to the builder's iPhone — working from anywhere over Tailscale. The winning moment: door opens in the house, phone buzzes in Arizona with a photo.

**Architecture:** The Mac gains an APNs sender (`macmini/apns.py`), a pure notification decision engine (`macmini/notify.py` — deciding *whether* and *what* to notify, with per-node cooldown and identity-aware text), a `POST /devices` endpoint that stores device tokens in a disk file, and a hook in the existing `/ingest/event/<node>` that fires a best-effort push. On iOS: the app requests notification permission, registers for remote notifications, and POSTs its device token to the Mac; a Notification Service Extension downloads the snapshot and attaches it (rich push). Tailscale is a builder-side install — no code, since the app already reads its base URL from Settings.

**Tech Stack:** Flask (Mac) **plus two new packages required specifically for APNs** — `httpx[http2]` (APNs mandates HTTP/2, which `requests` cannot do) and `PyJWT[crypto]` (APNs token auth requires ES256-signed JWTs). SwiftUI + `UserNotifications` + a `UNNotificationServiceExtension` (iOS). `unittest` (Mac), `XCTest` (iOS).

## Global Constraints

- **New Mac dependencies are permitted and required for this phase only:** `httpx[http2]`, `PyJWT[crypto]`. Add them to `macmini/requirements.txt`. This is a deliberate, documented relaxation of the prior "flask + requests only" rule — APNs cannot be implemented without HTTP/2 + ES256, and neither flask nor requests provides either. No OTHER new packages.
- Do NOT change existing route JSON shapes (`/`, `/chat`, `/app/chat`, `/events`, `/conversations`, `/nodes`, `/feed`, `/ingest/frame/<node>`, `/ingest/event/<node>`, `/snapshot/<id>`). `POST /devices` is additive. The push hook inside `/ingest/event/<node>` must not change that route's response shape or ever fail the ingest (best-effort, same philosophy as snapshot saving).
- APNs credentials are read from the environment / `.env` beside `server.py`, exactly like Supabase keys: `APNS_KEY_PATH` (path to the `.p8`), `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_BUNDLE_ID` (= `com.danefroelicher.Leofric`), `APNS_USE_SANDBOX` (default `1`). If any are missing, the whole push subsystem no-ops silently (like Supabase-unconfigured) — the server still runs and ingest still works. **These credentials are the builder's to generate in the Apple Developer portal; this plan never fabricates them.**
- Device tokens persist in `~/leofric-brain/devices.json` (a JSON list), never committed — add `macmini/devices.json` to `.gitignore` for the dev-checkout case, same as `macmini/snapshots/`.
- **Verification reality:** real APNs *delivery* cannot be verified without the builder's `.p8` key AND a real device token from the app running on a physical iPhone AND a physical remote test. This plan verifies everything else via unit tests (decision logic, JWT signing against a locally-generated throwaway ES256 key, payload shape via a mocked HTTP/2 transport, device registration, the ingest hook firing) and documents the exact builder-only steps in a setup runbook. Tasks that end at "unit-tested + builds, live delivery deferred" say so explicitly — do not claim live push verification.
- iOS: zero third-party dependencies; SwiftUI + Apple frameworks only; iOS 17+; `CODE_SIGN_STYLE: Automatic`, no hardcoded `DEVELOPMENT_TEAM`. The Notification Service Extension is a second target added via XcodeGen `project.yml`.
- Simulator target for iOS builds: `iPhone 17 Pro`, UDID `F40A0E50-DEC8-4A68-9332-3146E8D56711` (recover via `xcrun simctl list devices available | grep "iPhone 17 Pro"` if gone). Note: the Simulator cannot obtain a real APNs device token, so iOS tasks verify *compilation* and unit-testable logic only, not real registration.
- Run Mac tests: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server macmini.test_notify macmini.test_apns -v` (later tasks add the new test modules).
- Run iOS tests: `cd /Users/danefroelicher/Leofric/ios/LeofricApp && xcodebuild -project LeofricApp.xcodeproj -scheme LeofricApp -destination 'platform=iOS Simulator,id=F40A0E50-DEC8-4A68-9332-3146E8D56711' -derivedDataPath .build test`
- Adding a file in a new subdirectory has required `xcodegen generate` (from `ios/LeofricApp/`) + committing the regenerated `project.pbxproj` in every iOS task so far — expect it again. Ignore SourceKit-LSP false-positive diagnostics; trust only `xcodebuild` output.
- Mac deploy: `cp macmini/server.py ~/leofric-brain/server.py` (+ any new `macmini/*.py`), then `kill $(lsof -tiTCP:5000 -sTCP:LISTEN)` (launchd restarts via `com.leofric.brain`, KeepAlive).

---

### Task 1: Mac — notification decision engine (`macmini/notify.py`)

**Files:**
- Create: `macmini/notify.py`
- Create: `macmini/test_notify.py`

**Interfaces:**
- Produces: `build_alert(event_type: str, metadata: dict, node: str) -> dict | None` — returns `{"title": str, "body": str, "unknown": bool}` for a notifiable event, or `None` if this event type never notifies. `should_send(event_type: str, role: str | None, unknown: bool, node: str, now: float, last_sent: dict) -> bool` — applies the security-node + cooldown + unknown-always rules, and (as a side effect) records `now` in `last_sent[node]` when it returns True. Module constants `COOLDOWN_SECONDS = 60`, `NOTIFY_EVENT_TYPES = {"person", "identity"}`. Task 4 wires these into `/ingest/event`.

- [ ] **Step 1: Write the failing tests** — `macmini/test_notify.py`:

```python
"""Unit tests for the notification decision engine. Run:
    ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_notify -v
"""

import unittest

from macmini import notify


class BuildAlertTest(unittest.TestCase):
    def test_identity_known_person(self):
        alert = notify.build_alert("identity", {"name": "dane"}, "front-door")
        self.assertEqual(alert["title"], "Leofric")
        self.assertIn("Dane", alert["body"])
        self.assertIn("front-door", alert["body"])
        self.assertFalse(alert["unknown"])

    def test_identity_unknown_person(self):
        alert = notify.build_alert("identity", {"name": "unknown"}, "front-door")
        self.assertIn("UNKNOWN PERSON", alert["body"])
        self.assertTrue(alert["unknown"])

    def test_person_without_identity_is_unknown(self):
        alert = notify.build_alert("person", {"count": 1}, "front-door")
        self.assertTrue(alert["unknown"])
        self.assertIn("UNKNOWN PERSON", alert["body"])

    def test_motion_never_notifies(self):
        self.assertIsNone(notify.build_alert("motion", {"area": 5000}, "front-door"))


class ShouldSendTest(unittest.TestCase):
    def test_security_node_known_person_sends(self):
        last = {}
        self.assertTrue(notify.should_send("identity", "security", False, "d", 1000.0, last))
        self.assertEqual(last["d"], 1000.0)

    def test_assistant_node_never_sends(self):
        self.assertFalse(notify.should_send("identity", "assistant", False, "lr", 1000.0, {}))

    def test_none_role_treated_as_security(self):
        # A node whose role we don't know yet defaults to notifying (fail-safe:
        # better a spurious alert than a missed intruder).
        self.assertTrue(notify.should_send("identity", None, False, "d", 1000.0, {}))

    def test_cooldown_blocks_repeat_known_person(self):
        last = {"d": 1000.0}
        self.assertFalse(notify.should_send("identity", "security", False, "d", 1030.0, last))
        self.assertTrue(notify.should_send("identity", "security", False, "d", 1061.0, last))

    def test_unknown_always_sends_even_within_cooldown(self):
        last = {"d": 1000.0}
        self.assertTrue(notify.should_send("identity", "security", True, "d", 1005.0, last))

    def test_cooldown_is_per_node(self):
        last = {"a": 1000.0}
        self.assertTrue(notify.should_send("identity", "security", False, "b", 1005.0, last))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_notify -v`
Expected: `ModuleNotFoundError: No module named 'macmini.notify'`.

- [ ] **Step 3: Implement `macmini/notify.py`**

```python
"""
macmini/notify.py — pure notification decision logic (no I/O).

Separated from APNs sending and the Flask route so the "should we notify, and
what does it say" rules are unit-testable without a network or credentials.
"""

COOLDOWN_SECONDS = 60
NOTIFY_EVENT_TYPES = {"person", "identity"}


def build_alert(event_type, metadata, node):
    """Return {title, body, unknown} for a notifiable event, else None.

    A 'person' event (motion that resolved to a human but no face match) and an
    'identity' event with name 'unknown' both count as an unknown person — the
    loud case. A named identity is the calm case. Motion never notifies.
    """
    if event_type not in NOTIFY_EVENT_TYPES:
        return None
    name = (metadata or {}).get("name")
    unknown = event_type == "person" or not name or name == "unknown"
    if unknown:
        body = f"UNKNOWN PERSON at {node}"
    else:
        body = f"{name.capitalize()} at {node}"
    return {"title": "Leofric", "body": body, "unknown": unknown}


def should_send(event_type, role, unknown, node, now, last_sent):
    """Apply the notify rules; record the send time in last_sent on a True.

    Rules: only 'person'/'identity' at a security node (role None is treated
    as security — fail toward alerting); unknown persons always alert; known
    persons are rate-limited to one per COOLDOWN_SECONDS per node.
    """
    if event_type not in NOTIFY_EVENT_TYPES:
        return False
    if role == "assistant":
        return False
    if not unknown:
        previous = last_sent.get(node)
        if previous is not None and now - previous < COOLDOWN_SECONDS:
            return False
    last_sent[node] = now
    return True
```

- [ ] **Step 4: Run to verify pass**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_notify -v`
Expected: 10 tests, `OK`.

- [ ] **Step 5: Commit**

```bash
git add macmini/notify.py macmini/test_notify.py
git commit -m "brain: notification decision engine (identity-aware, per-node cooldown)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Mac — device token registration (`POST /devices`)

**Files:**
- Modify: `macmini/server.py` (config vars + `_load_device_tokens`/`_save_device_token` + the route, added after `/snapshot/<id>`)
- Modify: `macmini/test_server.py` (append to `ApiTest`)
- Modify: `/Users/danefroelicher/Leofric/.gitignore`

**Interfaces:**
- Produces: `POST /devices` body `{"token": "<hex>"}` → `200 {"ok": true}` (stores the token, de-duplicated); 400 on a missing/malformed token. `_load_device_tokens() -> list[str]` and `_save_device_token(token: str)` reading/writing `DEVICES_FILE`. Module var `DEVICES_FILE`, `_DEVICE_TOKEN_RE`. Task 4 reads tokens via `_load_device_tokens()`.

- [ ] **Step 1: Write the failing tests** — append to `macmini/test_server.py`'s `ApiTest`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server -v`
Expected: the 4 new tests fail (`AttributeError` on `DEVICES_FILE`/`_load_device_tokens`, 404 on `/devices`).

- [ ] **Step 3: Implement in `macmini/server.py`**

Add near the SNAPSHOT config block:

```python
# Device tokens for push notifications, one JSON list on disk (Mac-local).
DEVICES_FILE = os.getenv(
    "LEOFRIC_DEVICES_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "devices.json"),
)
_DEVICE_TOKEN_RE = re.compile(r"[0-9a-fA-F]{1,200}")
```

Add helpers + route after the `/snapshot/<id>` route:

```python
def _load_device_tokens():
    try:
        with open(DEVICES_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save_device_token(token):
    tokens = _load_device_tokens()
    if token not in tokens:
        tokens.append(token)
        os.makedirs(os.path.dirname(os.path.abspath(DEVICES_FILE)), exist_ok=True)
        with open(DEVICES_FILE, "w") as f:
            json.dump(tokens, f)


@app.post("/devices")
def register_device():
    """iOS app registers its APNs device token here so the Mac can push to it."""
    data = request.get_json(force=True, silent=True) or {}
    token = (data.get("token") or "").strip()
    if not token or not _DEVICE_TOKEN_RE.fullmatch(token):
        return jsonify(error="missing or malformed 'token'"), 400
    _save_device_token(token)
    return jsonify(ok=True)
```

Add `import json` to the imports at the top of `server.py` (after `import os`) — it is NOT currently imported (the file's imports are `os`, `re`, `threading`, `time`, `requests`, `flask`), and `_load_device_tokens`/`_save_device_token` need it.

- [ ] **Step 4: Add `.gitignore` entry** — under the snapshots line:

```
# Device tokens are written on the Mac only, never committed.
macmini/devices.json
```

- [ ] **Step 5: Run the full suite; all pass**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server -v`
Expected: 32 tests, `OK`.

- [ ] **Step 6: Commit**

```bash
git add macmini/server.py macmini/test_server.py .gitignore
git commit -m "brain: POST /devices — register iOS APNs device tokens (file-backed)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Mac — APNs client (`macmini/apns.py`)

**Files:**
- Create: `macmini/apns.py`
- Create: `macmini/test_apns.py`
- Modify: `macmini/requirements.txt`

**Interfaces:**
- Produces: `APNsClient(key_path, key_id, team_id, bundle_id, use_sandbox=True, client=None)` with `.send(token: str, title: str, body: str, snapshot_id: str | None, mutable: bool) -> bool` (returns True on APNs 200, False otherwise; never raises). `_build_jwt()` (ES256, cached ~50 min) and `_payload(title, body, snapshot_id, mutable)` are separately testable. The `client` param injects an `httpx.Client` (real one built internally if None) so tests pass a mock transport. Task 4 constructs one `APNsClient` from config and calls `.send(...)`.

- [ ] **Step 1: Add the dependencies** — append to `macmini/requirements.txt`:

```
# Push notifications (Phase 2E). APNs mandates HTTP/2 (requests can't) and
# ES256 JWT auth — these two packages are the minimum to do that.
httpx[http2]
PyJWT[crypto]
```

Install them into the deployment venv now (needed for the tests to run):
```bash
~/leofric-brain/venv/bin/pip install 'httpx[http2]' 'PyJWT[crypto]'
```
Expected: installs httpx, h2, pyjwt, cryptography successfully.

- [ ] **Step 2: Write the failing tests** — `macmini/test_apns.py`. These generate a throwaway ES256 key so JWT signing is exercised for real, and inject a mock `httpx` transport so no network is touched:

```python
"""Unit tests for the APNs client. Run:
    ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_apns -v
Uses a locally-generated throwaway ES256 key — no real Apple credentials.
"""

import os
import tempfile
import unittest

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from macmini.apns import APNsClient


def _write_test_p8(path):
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with open(path, "wb") as f:
        f.write(pem)
    return key.public_key()


class APNsClientTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.key_path = os.path.join(self.tmp.name, "key.p8")
        self.public_key = _write_test_p8(self.key_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _client(self, transport):
        http = httpx.Client(transport=transport)
        return APNsClient(
            key_path=self.key_path, key_id="KEY123", team_id="TEAM123",
            bundle_id="com.danefroelicher.Leofric", use_sandbox=True, client=http,
        )

    def test_jwt_is_valid_es256_with_headers_and_claims(self):
        client = self._client(httpx.MockTransport(lambda r: httpx.Response(200)))
        token = client._build_jwt()
        header = jwt.get_unverified_header(token)
        self.assertEqual(header["alg"], "ES256")
        self.assertEqual(header["kid"], "KEY123")
        decoded = jwt.decode(token, self.public_key, algorithms=["ES256"])
        self.assertEqual(decoded["iss"], "TEAM123")
        self.assertIn("iat", decoded)

    def test_payload_shape(self):
        client = self._client(httpx.MockTransport(lambda r: httpx.Response(200)))
        payload = client._payload("Leofric", "UNKNOWN PERSON at door", "leofric-1", True)
        self.assertEqual(payload["aps"]["alert"]["title"], "Leofric")
        self.assertEqual(payload["aps"]["alert"]["body"], "UNKNOWN PERSON at door")
        self.assertEqual(payload["aps"]["mutable-content"], 1)
        self.assertEqual(payload["snapshot_id"], "leofric-1")

    def test_send_success_returns_true_and_hits_correct_url(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["topic"] = request.headers.get("apns-topic")
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(200)

        client = self._client(httpx.MockTransport(handler))
        ok = client.send("devtoken123", "Leofric", "Dane at door", "leofric-1", True)
        self.assertTrue(ok)
        self.assertEqual(seen["url"], "https://api.sandbox.push.apple.com/3/device/devtoken123")
        self.assertEqual(seen["topic"], "com.danefroelicher.Leofric")
        self.assertTrue(seen["auth"].startswith("bearer "))

    def test_send_uses_production_host_when_not_sandbox(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            return httpx.Response(200)

        http = httpx.Client(transport=httpx.MockTransport(handler))
        client = APNsClient(
            key_path=self.key_path, key_id="K", team_id="T",
            bundle_id="com.danefroelicher.Leofric", use_sandbox=False, client=http,
        )
        client.send("tok", "t", "b", None, False)
        self.assertTrue(seen["url"].startswith("https://api.push.apple.com/"))

    def test_send_non_200_returns_false(self):
        client = self._client(httpx.MockTransport(lambda r: httpx.Response(410)))
        self.assertFalse(client.send("tok", "t", "b", None, False))

    def test_send_never_raises_on_transport_error(self):
        def boom(request):
            raise httpx.ConnectError("down")

        client = self._client(httpx.MockTransport(boom))
        self.assertFalse(client.send("tok", "t", "b", None, False))
```

- [ ] **Step 3: Run to verify failure**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_apns -v`
Expected: `ModuleNotFoundError: No module named 'macmini.apns'`.

- [ ] **Step 4: Implement `macmini/apns.py`**

```python
"""
macmini/apns.py — Apple Push Notification service client (token auth).

APNs requires HTTP/2 (httpx) and an ES256-signed JWT (PyJWT) built from the
team's .p8 auth key. This class is credential-driven and self-contained; it is
constructed only when APNs env vars are present (see server.py). Sending is
best-effort — send() never raises, returning False on any failure so a push
problem can never disrupt event ingest.
"""

import time

import httpx
import jwt

_JWT_TTL_SECONDS = 3000  # Apple wants a fresh token every 20-60 min; refresh at 50.


class APNsClient:
    def __init__(self, key_path, key_id, team_id, bundle_id, use_sandbox=True, client=None):
        with open(key_path) as f:
            self._key = f.read()
        self.key_id = key_id
        self.team_id = team_id
        self.bundle_id = bundle_id
        host = "api.sandbox.push.apple.com" if use_sandbox else "api.push.apple.com"
        self._base = f"https://{host}"
        self._client = client or httpx.Client(http2=True, timeout=10)
        self._jwt = None
        self._jwt_at = 0.0

    def _build_jwt(self):
        now = time.time()
        if self._jwt is None or now - self._jwt_at > _JWT_TTL_SECONDS:
            self._jwt = jwt.encode(
                {"iss": self.team_id, "iat": int(now)},
                self._key,
                algorithm="ES256",
                headers={"kid": self.key_id},
            )
            self._jwt_at = now
        return self._jwt

    def _payload(self, title, body, snapshot_id, mutable):
        aps = {"alert": {"title": title, "body": body}, "sound": "default"}
        if mutable:
            aps["mutable-content"] = 1
        payload = {"aps": aps}
        if snapshot_id:
            payload["snapshot_id"] = snapshot_id
        return payload

    def send(self, token, title, body, snapshot_id, mutable):
        """POST one notification. Returns True on APNs 200, else False. Never raises."""
        try:
            resp = self._client.post(
                f"{self._base}/3/device/{token}",
                json=self._payload(title, body, snapshot_id, mutable),
                headers={
                    "authorization": f"bearer {self._build_jwt()}",
                    "apns-topic": self.bundle_id,
                    "apns-push-type": "alert",
                    "apns-priority": "10",
                },
            )
            return resp.status_code == 200
        except Exception:
            return False
```

- [ ] **Step 5: Run to verify pass**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_apns -v`
Expected: 7 tests, `OK`.

- [ ] **Step 6: Commit**

```bash
git add macmini/apns.py macmini/test_apns.py macmini/requirements.txt
git commit -m "brain: APNs client — HTTP/2 + ES256 JWT push sender

Adds httpx[http2] + PyJWT[crypto] (required for APNs; documented in the
Phase 2E plan). JWT signing is unit-tested against a throwaway ES256 key
and the send path against a mocked HTTP/2 transport — real Apple delivery
awaits the builder's .p8 key and a device token.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Mac — wire push into `/ingest/event` + APNs config

**Files:**
- Modify: `macmini/server.py` (config, a module-level `_last_notified` dict + APNs client init, a `_maybe_notify` helper, and a call inside `ingest_event`)
- Modify: `macmini/test_server.py` (append)

**Interfaces:**
- Consumes: `notify.build_alert`/`notify.should_send` (Task 1), `_load_device_tokens` (Task 2), `APNsClient` (Task 3).
- Produces: `_maybe_notify(event_type, metadata, node, snapshot_id)` — best-effort; builds the alert, checks `should_send` against the node's cached role and `_last_notified`, and sends to every registered device via the module `_apns` client (or no-ops if APNs unconfigured / no client). Called at the end of `ingest_event` before it returns.

- [ ] **Step 1: Write the failing tests** — append to `macmini/test_server.py`'s `ApiTest`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server -v`
Expected: the 4 new tests fail (`AttributeError` on `_apns`/`_last_notified`).

- [ ] **Step 3: Implement in `macmini/server.py`**

Add `from macmini import notify` (or `import notify` matching the existing import style — check how the server imports sibling modules; if it runs as a top-level script `server.py`, a plain `import notify` won't resolve when deployed as `~/leofric-brain/server.py` with `notify.py` beside it — so mirror whatever pattern works; in the deployment, `server.py` and `notify.py`/`apns.py` sit together in `~/leofric-brain/`, so a plain `import notify` / `import apns` is correct for deployment, while the tests import `macmini.notify`. To satisfy both, use a try/except import shim near the top:

```python
try:                       # deployed flat in ~/leofric-brain/
    import notify
    from apns import APNsClient
except ImportError:        # running as the macmini package (tests)
    from macmini import notify
    from macmini.apns import APNsClient
```

Add config + APNs client init after the DEVICES_FILE block:

```python
APNS_KEY_PATH = os.getenv("APNS_KEY_PATH", "")
APNS_KEY_ID = os.getenv("APNS_KEY_ID", "")
APNS_TEAM_ID = os.getenv("APNS_TEAM_ID", "")
APNS_BUNDLE_ID = os.getenv("APNS_BUNDLE_ID", "com.danefroelicher.Leofric")
APNS_USE_SANDBOX = os.getenv("APNS_USE_SANDBOX", "1").lower() not in ("0", "false", "no")

_last_notified = {}  # node -> epoch of last push, for cooldown

def _make_apns():
    if not (APNS_KEY_PATH and APNS_KEY_ID and APNS_TEAM_ID and os.path.exists(APNS_KEY_PATH)):
        return None
    try:
        return APNsClient(APNS_KEY_PATH, APNS_KEY_ID, APNS_TEAM_ID,
                          APNS_BUNDLE_ID, use_sandbox=APNS_USE_SANDBOX)
    except Exception:
        return None

_apns = _make_apns()
```

Add the helper near `_prune_snapshots`:

```python
def _maybe_notify(event_type, metadata, node, snapshot_id):
    """Best-effort push for a person/identity event at a security node. Never
    raises — a notification problem must not disrupt event ingest."""
    if _apns is None:
        return
    try:
        alert = notify.build_alert(event_type, metadata or {}, node)
        if alert is None:
            return
        role = _frames.get(node, {}).get("role")
        if not notify.should_send(event_type, role, alert["unknown"], node,
                                  time.time(), _last_notified):
            return
        for token in _load_device_tokens():
            _apns.send(token, alert["title"], alert["body"], snapshot_id, True)
    except Exception:
        pass
```

Call it at the end of `ingest_event`, right before `return jsonify(ok=True, snapshot_id=snapshot_id)`:

```python
    _maybe_notify(event_type, data.get("metadata") or {}, node, snapshot_id)
    return jsonify(ok=True, snapshot_id=snapshot_id)
```

- [ ] **Step 4: Run the full suite; all pass**

Run: `cd /Users/danefroelicher/Leofric && ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_server macmini.test_notify macmini.test_apns -v`
Expected: all pass (36 server + 10 notify + 7 apns).

- [ ] **Step 5: Commit**

```bash
git add macmini/server.py macmini/test_server.py
git commit -m "brain: fire best-effort push on person/identity events at ingest

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Mac — deploy + verify everything except real APNs delivery

**Files:** none created; deploys the new/changed Mac files.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: the live Mac serves `/devices` and runs the push hook (no-op until the builder adds APNs creds).

- [ ] **Step 1: Deploy all Mac files**

```bash
for f in server.py notify.py apns.py; do cp /Users/danefroelicher/Leofric/macmini/$f ~/leofric-brain/$f; done
diff ~/leofric-brain/server.py /Users/danefroelicher/Leofric/macmini/server.py && echo IDENTICAL
~/leofric-brain/venv/bin/pip install 'httpx[http2]' 'PyJWT[crypto]' >/dev/null 2>&1 && echo deps-ok
kill $(lsof -tiTCP:5000 -sTCP:LISTEN); sleep 4
curl -s http://localhost:5000/
```
Expected: `IDENTICAL`, `deps-ok`, then the health JSON (server boots even with APNs unconfigured — `_apns` is None).

- [ ] **Step 2: Verify device registration live**

```bash
curl -s -X POST http://localhost:5000/devices -H 'Content-Type: application/json' -d '{"token":"deadbeefcafe"}'
cat ~/leofric-brain/devices.json
```
Expected: `{"ok":true}` and the file contains `["deadbeefcafe"]`.

- [ ] **Step 3: Verify the push hook no-ops safely with APNs unconfigured** (the Pi is streaming, so a manual identity event triggers `_maybe_notify`, which should return cleanly since `_apns` is None)

```bash
curl -s -X POST http://localhost:5000/ingest/event/leofric \
  -H 'Content-Type: application/json' -d '{"event_type":"identity","metadata":{"name":"dane"}}'
```
Expected: `{"ok":true,"snapshot_id":"..."}` — ingest succeeds, no crash, no push (APNs not configured). Clean up the test token: `rm -f ~/leofric-brain/devices.json`.

- [ ] **Step 4: Push**

```bash
git push
```

---

### Task 6: iOS — notification registration + `LeofricAPI.registerDevice`

**Files:**
- Create: `ios/LeofricApp/LeofricApp/Notifications/PushRegistrar.swift`
- Modify: `ios/LeofricApp/LeofricApp/LeofricApp.swift` (adopt an `AppDelegate` via `UIApplicationDelegateAdaptor`)
- Modify: `ios/LeofricApp/LeofricApp/Networking/LeofricAPI.swift` (`registerDevice`)
- Modify: `ios/LeofricApp/LeofricAppTests/LeofricAPITests.swift`
- Modify: `ios/LeofricApp/project.yml` (add the Push Notifications capability / entitlement + App Group)

**Interfaces:**
- Produces: `LeofricAPI.registerDevice(token: String) async throws` (POSTs `{"token": token}` to `/devices`). `AppDelegate: NSObject, UIApplicationDelegate` that on launch requests notification auth + `registerForRemoteNotifications()`, and on `didRegisterForRemoteNotificationsWithDeviceToken` hex-encodes the token and POSTs it via `LeofricAPI` built from the shared base URL. `PushRegistrar` holds the small helper logic (hex-encoding, building the API) so it's unit-testable.

- [ ] **Step 1: Write the failing test** — append to `LeofricAPITests.swift`:

```swift
    func testRegisterDevicePostsToken() async throws {
        var capturedBody: Data?
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.path, "/devices")
            capturedBody = request.httpBodyStreamData() ?? request.httpBody
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data("{\"ok\":true}".utf8))
        }
        try await makeAPI().registerDevice(token: "abc123")
        let json = try JSONSerialization.jsonObject(with: try XCTUnwrap(capturedBody)) as? [String: Any]
        XCTAssertEqual(json?["token"] as? String, "abc123")
    }

    func testHexEncodesDeviceToken() {
        let raw = Data([0xAB, 0x01, 0xFF])
        XCTAssertEqual(PushRegistrar.hexString(from: raw), "ab01ff")
    }
```

- [ ] **Step 2: Run to verify failure**

Run: the iOS test command from Global Constraints.
Expected: `** TEST FAILED **` — `no member 'registerDevice'` / `cannot find 'PushRegistrar'`.

- [ ] **Step 3: Add `registerDevice` to `LeofricAPI.swift`** (after `sendAppChat`):

```swift
    func registerDevice(token: String) async throws {
        var request = URLRequest(url: baseURL.appendingPathComponent("devices"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["token": token])
        let (_, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw LeofricAPIError.invalidResponse }
        guard http.statusCode == 200 else { throw LeofricAPIError.httpStatus(http.statusCode) }
    }
```

- [ ] **Step 4: Write `ios/LeofricApp/LeofricApp/Notifications/PushRegistrar.swift`**

```swift
import Foundation
import UIKit
import UserNotifications

/// Requests notification permission, registers for remote notifications, and
/// ships the resulting APNs device token to the Mac. The Simulator can't get a
/// real token, so this only does anything meaningful on a physical device.
enum PushRegistrar {
    static func hexString(from token: Data) -> String {
        token.map { String(format: "%02x", $0) }.joined()
    }

    static func requestAndRegister() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            guard granted else { return }
            DispatchQueue.main.async {
                UIApplication.shared.registerForRemoteNotifications()
            }
        }
    }

    static func sendToken(_ token: Data) {
        let hex = hexString(from: token)
        let settings = AppSettings()
        guard let baseURL = settings.baseURL else { return }
        Task { try? await LeofricAPI(baseURL: baseURL).registerDevice(token: hex) }
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        PushRegistrar.requestAndRegister()
        return true
    }

    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        PushRegistrar.sendToken(deviceToken)
    }

    func application(_ application: UIApplication,
                     didFailToRegisterForRemoteNotificationsWithError error: Error) {
        // Expected on the Simulator; silent on device unless entitlement missing.
    }
}
```

- [ ] **Step 5: Adopt the delegate in `LeofricApp.swift`** — replace the file:

```swift
import SwiftUI

@main
struct LeofricApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            RootTabView()
        }
    }
}
```

- [ ] **Step 6: Add the Push Notifications entitlement + App Group to `project.yml`** — under the `LeofricApp` target, add an `entitlements` block (XcodeGen writes the file):

```yaml
    entitlements:
      path: LeofricApp/LeofricApp.entitlements
      properties:
        aps-environment: development
        com.apple.security.application-groups:
          - group.com.danefroelicher.Leofric
```

Then `cd ios/LeofricApp && xcodegen generate`.

- [ ] **Step 7: Build + test**

Run the iOS test command.
Expected: `** BUILD SUCCEEDED **`, `** TEST SUCCEEDED **`, 34 tests (32 prior + 2 new). (The Simulator won't actually register for remote notifications — that's expected and not a failure; we're verifying compilation + the API/hex logic.)

- [ ] **Step 8: Commit**

```bash
cd /Users/danefroelicher/Leofric
git add ios/LeofricApp/LeofricApp/Notifications/ ios/LeofricApp/LeofricApp/LeofricApp.swift \
        ios/LeofricApp/LeofricApp/Networking/LeofricAPI.swift \
        ios/LeofricApp/LeofricAppTests/LeofricAPITests.swift \
        ios/LeofricApp/project.yml ios/LeofricApp/LeofricApp.xcodeproj
git commit -m "ios: register for push notifications + POST device token to the Mac

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: iOS — Notification Service Extension (rich push with photo)

**Files:**
- Create: `ios/LeofricApp/NotificationService/NotificationService.swift`
- Create: `ios/LeofricApp/NotificationService/Info.plist` (via XcodeGen properties)
- Modify: `ios/LeofricApp/LeofricApp/Settings/AppSettings.swift` (mirror `baseURLString` into the shared App Group so the extension can read it)
- Modify: `ios/LeofricApp/project.yml` (add the extension target + its App Group entitlement)

**Interfaces:**
- Consumes: the App Group `group.com.danefroelicher.Leofric` (Task 6) and the `snapshot_id` the Mac puts in the APNs payload (Task 4).
- Produces: a `NotificationService` extension that, on receiving a `mutable-content` push, reads the base URL from the shared App Group, downloads `<baseURL>/snapshot/<snapshot_id>`, and attaches it to the notification. `AppSettings` now writes `baseURLString` to the shared `UserDefaults(suiteName:)` too.

- [ ] **Step 1: Mirror the base URL into the App Group in `AppSettings.swift`** — change the `didSet` so it also writes to the shared suite. Read the current file first; change the property to:

```swift
    @Published var baseURLString: String {
        didSet {
            defaults.set(baseURLString, forKey: Keys.baseURLString)
            UserDefaults(suiteName: Self.appGroup)?.set(baseURLString, forKey: Keys.baseURLString)
        }
    }
```
and add near the other statics:
```swift
    static let appGroup = "group.com.danefroelicher.Leofric"
```

- [ ] **Step 2: Write `ios/LeofricApp/NotificationService/NotificationService.swift`**

```swift
import UserNotifications

/// Downloads the event snapshot referenced by `snapshot_id` and attaches it,
/// turning the text push into a rich notification with the photo. Reads the
/// Mac's base URL from the shared App Group (written by the main app's
/// AppSettings). Falls back to the plain text notification on any failure.
final class NotificationService: UNNotificationServiceExtension {
    private var contentHandler: ((UNNotificationContent) -> Void)?
    private var bestAttempt: UNMutableNotificationContent?

    override func didReceive(_ request: UNNotificationRequest,
                             withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void) {
        self.contentHandler = contentHandler
        let content = (request.content.mutableCopy() as? UNMutableNotificationContent)
        bestAttempt = content
        guard let content,
              let snapshotID = request.content.userInfo["snapshot_id"] as? String,
              let baseString = UserDefaults(suiteName: "group.com.danefroelicher.Leofric")?
                  .string(forKey: "leofric.baseURLString"),
              let base = URL(string: baseString)
        else { contentHandler(bestAttempt ?? request.content); return }

        let url = base.appendingPathComponent("snapshot").appendingPathComponent(snapshotID)
        let task = URLSession.shared.downloadTask(with: url) { tempURL, _, _ in
            defer { contentHandler(content) }
            guard let tempURL else { return }
            let dest = FileManager.default.temporaryDirectory
                .appendingPathComponent(snapshotID + ".jpg")
            try? FileManager.default.moveItem(at: tempURL, to: dest)
            if let attachment = try? UNNotificationAttachment(identifier: snapshotID, url: dest) {
                content.attachments = [attachment]
            }
        }
        task.resume()
    }

    override func serviceExtensionTimeWillExpire() {
        if let handler = contentHandler, let content = bestAttempt {
            handler(content)
        }
    }
}
```

- [ ] **Step 3: Add the extension target to `project.yml`** — add under `targets:` and register it as a dependency of the app so it's embedded:

```yaml
  NotificationService:
    type: app-extension
    platform: iOS
    sources:
      - path: NotificationService
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: com.danefroelicher.Leofric.NotificationService
    info:
      path: NotificationService/Info.plist
      properties:
        CFBundleDisplayName: LeofricNotification
        NSExtension:
          NSExtensionPointIdentifier: com.apple.usernotifications.service
          NSExtensionPrincipalClass: $(PRODUCT_MODULE_NAME).NotificationService
    entitlements:
      path: NotificationService/NotificationService.entitlements
      properties:
        com.apple.security.application-groups:
          - group.com.danefroelicher.Leofric
```

And add to the `LeofricApp` target a `dependencies:` entry:
```yaml
    dependencies:
      - target: NotificationService
        embed: true
```

Then `cd ios/LeofricApp && xcodegen generate`.

- [ ] **Step 4: Build + test**

Run the iOS test command (build both targets + run tests).
Expected: `** BUILD SUCCEEDED **` (app + extension both compile), `** TEST SUCCEEDED **`, 34 tests (no new unit tests — the extension is not unit-testable without a device receiving a push; this task verifies it compiles and is wired as an embedded extension).

- [ ] **Step 5: Commit**

```bash
cd /Users/danefroelicher/Leofric
git add ios/LeofricApp/NotificationService/ ios/LeofricApp/LeofricApp/Settings/AppSettings.swift \
        ios/LeofricApp/project.yml ios/LeofricApp/LeofricApp.xcodeproj
git commit -m "ios: Notification Service Extension — attach snapshot photo to pushes

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: Docs — Phase 2E setup runbook + ROADMAP close-out

**Files:**
- Create: `docs/PHASE_2E_SETUP.md`
- Modify: `docs/ROADMAP.md`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write `docs/PHASE_2E_SETUP.md`** — a builder-facing runbook covering exactly the steps only the builder can do, since the code is complete but real delivery is unverifiable without them. Include, as clear numbered steps:
  1. **Apple Developer portal:** create an APNs Auth Key (Keys → +, enable "Apple Push Notifications service"), download the `.p8` once, record the **Key ID** and your **Team ID**. Enable the Push Notifications + App Groups capabilities for the `com.danefroelicher.Leofric` App ID, and create the App Group `group.com.danefroelicher.Leofric`.
  2. **Mac config:** copy the `.p8` to `~/leofric-brain/`, and add to `~/leofric-brain/.env`: `APNS_KEY_PATH`, `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_BUNDLE_ID=com.danefroelicher.Leofric`, `APNS_USE_SANDBOX=1` (1 for development builds, 0 for TestFlight/App Store). Restart the brain (`kill $(lsof -tiTCP:5000 -sTCP:LISTEN)`).
  3. **Xcode:** open the project, select your team for both the app and the NotificationService targets, confirm the Push Notifications + App Groups capabilities are present, build to your physical iPhone, grant the notification permission prompt. Confirm the token registered: `cat ~/leofric-brain/devices.json` should show a 64-hex-char token.
  4. **Tailscale:** install Tailscale on the Mac and the iPhone, sign both into the same account; in the app's Nodes tab set the Mac address to the Tailscale hostname (or MagicDNS name).
  5. **The Arizona test:** leave home / turn off WiFi on the phone (cellular + Tailscale), have someone trigger a person event at the node, confirm the push arrives with the photo, and that tapping it opens the app and the live feed loads over Tailscale.
  Also document the `aps-environment` gotcha (must be `development` for Xcode-signed builds → `APNS_USE_SANDBOX=1`; `production` for TestFlight → `APNS_USE_SANDBOX=0`), and that a `.p8` downloads only once.

- [ ] **Step 2: Update `docs/ROADMAP.md`** — in the `### 2E` section, check off the `[CODE]` items, leave the `[YOU]` items unchecked, and add a completion note stating: code complete and unit-tested (Mac decision engine + APNs client with JWT signing verified against a throwaway key + device registration + ingest push hook + iOS registration + service extension); **live delivery deferred** to the builder's testing pass since it requires their `.p8` key, a real device token, and a physical remote test; setup steps in `docs/PHASE_2E_SETUP.md`. Do not mark the `[DECISION]` Phase 2 review line — that's for the builder after the on-device pass.

- [ ] **Step 3: Commit and push**

```bash
cd /Users/danefroelicher/Leofric
git add docs/PHASE_2E_SETUP.md docs/ROADMAP.md
git commit -m "docs: Phase 2E setup runbook + roadmap (code complete, live test deferred)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
git push
```
