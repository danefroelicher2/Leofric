"""
macmini/server.py — Leofric's brain + app API (runs on the Mac Mini).

A small Flask server with two jobs:

1. Brain (Phase 1): the Pi POSTs transcribed speech to /chat; this forwards it
   to a local Ollama model (Llama 3.2) with Leofric's persona plus the recent
   conversation, and returns the model's text reply. Heavy inference stays on
   the Mac; the Pi stays light.

2. App API (Phase 2A): serves the data the iOS app consumes.
   - The Pi pushes camera frames to POST /ingest/frame/<node>; the latest frame
     per node is kept in memory and re-broadcast as an MJPEG stream at /feed.
   - /events and /conversations proxy Supabase (the Pi writes those tables) so
     the app talks only to the Mac.
   - /nodes reports which sensing nodes are alive, judged by frame recency.

Secrets: /events and /conversations need SUPABASE_URL + SUPABASE_KEY. They are
read from the environment, falling back to a .env file next to this script
(~/leofric-brain/.env in deployment — never committed).

Run on the Mac Mini (see macmini/README.md):
    python3 server.py
Binds 0.0.0.0:5000 so the Pi and iPhones on the LAN can reach it.
"""

import json
import os
import re
import threading
import time

import requests
from flask import Flask, Response, jsonify, request, send_file

try:                       # notify is pure Python — required, no third-party deps
    import notify
except ImportError:        # running as the macmini package (tests)
    from macmini import notify

APNsClient = None          # push is optional: if httpx/PyJWT aren't installed,
try:                       # the brain still runs, push just no-ops.
    try:
        from apns import APNsClient          # deployed flat in ~/leofric-brain/
    except ImportError:
        from macmini.apns import APNsClient  # macmini package layout (tests)
except Exception:          # apns module missing OR its deps (httpx/PyJWT) absent
    APNsClient = None


def _load_dotenv():
    """Load KEY=VALUE lines from .env beside this script into os.environ.

    Real environment variables win over the file. Tiny and dependency-free on
    purpose — the deployment is a bare venv with only flask + requests.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("LEOFRIC_MODEL", "llama3.2")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# A node is "online" if it pushed a frame within this window. The Pi streams
# several frames per second, so 15s tolerates WiFi hiccups without lying.
NODE_ONLINE_WINDOW_SECONDS = 15
FEED_FPS = 15  # re-broadcast rate of /feed (matches the Pi's default push rate)
# Quiet-gap re-send of the last frame: keeps the app's 10s stall detector fed
# without re-broadcasting duplicates at full rate when the node sends slowly.
FEED_KEEPALIVE_SECONDS = 1.0
MAX_FRAME_BYTES = 5 * 1024 * 1024  # reject absurd uploads; 720p JPEG is ~100 KB

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

# Device tokens for push notifications, one JSON list on disk (Mac-local).
DEVICES_FILE = os.getenv(
    "LEOFRIC_DEVICES_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "devices.json"),
)
_DEVICE_TOKEN_RE = re.compile(r"[0-9a-fA-F]{1,200}")

# APNs (push notifications): unconfigured by default — _make_apns() returns
# None and _maybe_notify() becomes a no-op until a real .p8 key is deployed.
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

SYSTEM_PROMPT = (
    "You are Leofric, a local home intelligence system running on the builder's "
    "own hardware. You watch and listen through sensors and answer through text. "
    "You are concise, calm, and direct. Keep replies short unless asked for detail."
)

app = Flask(__name__)

# Latest frame per node: {node_id: {"jpeg": bytes, "at": epoch_seconds}}.
# In-memory only — the feed is live TV, not a recording (privacy is a feature).
_frames = {}
_frames_lock = threading.Lock()


@app.get("/")
def health():
    return jsonify(status="ok", service="leofric-brain", model=MODEL)


@app.post("/chat")
def chat():
    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []  # list of {"role", "content"}
    if not message:
        return jsonify(error="missing 'message'"), 400

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    try:
        resp = requests.post(
            OLLAMA_URL,
            # keep_alive=-1 keeps the model resident in RAM between requests,
            # regardless of which Ollama launch mechanism owns the port.
            json={"model": MODEL, "messages": messages, "stream": False,
                  "keep_alive": -1},
            timeout=120,
        )
        resp.raise_for_status()
        reply = resp.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        return jsonify(error=f"ollama request failed: {e}"), 502

    return jsonify(response=reply)


# --- Phase 2A: frame ingest + live feed -------------------------------------


@app.post("/ingest/frame/<node>")
def ingest_frame(node):
    if not _NODE_RE.fullmatch(node):
        return jsonify(error="invalid node name"), 400
    jpeg = request.get_data()
    if not jpeg or len(jpeg) > MAX_FRAME_BYTES:
        return jsonify(error="expected a JPEG body under 5 MB"), 400
    if not jpeg.startswith(b"\xff\xd8"):  # JPEG magic — cheap sanity check
        return jsonify(error="body is not a JPEG"), 400
    role = request.headers.get("X-Node-Role") or None
    with _frames_lock:
        _frames[node] = {"jpeg": jpeg, "at": time.time(), "role": role}
    return jsonify(ok=True)


def _latest_frame(node):
    with _frames_lock:
        entry = _frames.get(node)
        return (entry["jpeg"], entry["at"]) if entry else (None, 0.0)


def _mjpeg_stream(node):
    """Yield the latest frame as multipart MJPEG until the client disconnects.

    Only NEW frames are sent (the node's ingest timestamp is the change
    signal); an unchanged frame is re-sent once per FEED_KEEPALIVE_SECONDS so
    players that measure liveness by inter-frame gaps don't stall during quiet
    moments. And if the node's frames go STALE (Pi died mid-stream), the
    stream ends instead of re-broadcasting the last frame forever — a frozen
    image that looks live is the worst failure mode for a remote security
    camera. Ending hands off to the app's reconnect loop, which then gets
    /feed's honest 503.
    """
    last_sent_ingest_at = 0.0
    last_yield_at = 0.0
    while True:
        jpeg, at = _latest_frame(node)
        now = time.time()
        if jpeg is None or now - at > NODE_ONLINE_WINDOW_SECONDS:
            return
        if at != last_sent_ingest_at or now - last_yield_at >= FEED_KEEPALIVE_SECONDS:
            last_sent_ingest_at = at
            last_yield_at = now
            yield (
                b"--leofricframe\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                + jpeg + b"\r\n"
            )
        time.sleep(1.0 / FEED_FPS)


@app.get("/feed")
def feed():
    node = request.args.get("node", "leofric")
    jpeg, at = _latest_frame(node)
    if jpeg is None or time.time() - at > NODE_ONLINE_WINDOW_SECONDS:
        return jsonify(error=f"no live frames from node {node!r}"), 503
    return Response(
        _mjpeg_stream(node),
        mimetype="multipart/x-mixed-replace; boundary=leofricframe",
    )


def _prune_snapshots():
    entries = []
    for name in os.listdir(SNAPSHOT_DIR):
        if not name.endswith(".jpg"):
            continue
        path = os.path.join(SNAPSHOT_DIR, name)
        try:
            entries.append((os.path.getmtime(path), path))
        except OSError:
            continue  # vanished between listdir and stat — skip it
    entries.sort()
    for _, path in entries[: max(0, len(entries) - SNAPSHOT_KEEP)]:
        try:
            os.remove(path)
        except OSError:
            pass


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
        tokens = _load_device_tokens()
        sent = sum(1 for t in tokens if _apns.send(t, alert["title"], alert["body"], snapshot_id, True))
        app.logger.info("push sent: %r -> %d/%d device(s)", alert["body"], sent, len(tokens))
    except Exception as e:
        app.logger.warning("push failed: %s", e)


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
    _maybe_notify(event_type, data.get("metadata") or {}, node, snapshot_id)
    return jsonify(ok=True, snapshot_id=snapshot_id)


@app.get("/snapshot/<snapshot_id>")
def snapshot(snapshot_id):
    if not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        return jsonify(error="not found"), 404
    path = os.path.join(SNAPSHOT_DIR, snapshot_id + ".jpg")
    if not os.path.exists(path):
        return jsonify(error="not found"), 404
    return send_file(path, mimetype="image/jpeg")


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


@app.get("/nodes")
def nodes():
    now = time.time()
    with _frames_lock:
        seen = {n: e["at"] for n, e in _frames.items()}
        roles = {n: e.get("role") for n, e in _frames.items()}
    # Fallback: a node that isn't streaming (feature off, brain rebooted) still
    # counts as recently-seen if it logged an event to Supabase.
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
    return jsonify(nodes=result)


def _iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(epoch))


# --- Phase 2A: Supabase-backed history ---------------------------------------


def _supabase_get(table, params):
    """One PostgREST query. Raises on any failure; callers map that to a 502."""
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _supabase_post(table, row):
    """Insert one row via PostgREST. Raises on any failure; callers decide
    whether that should fail the request or just be logged and swallowed."""
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=row,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        },
        timeout=10,
    )
    resp.raise_for_status()


def _supabase_last_event_times():
    """{node_id: last event epoch} from recent events; empty dict on failure."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return {}
    try:
        rows = _supabase_get(
            "events",
            {"select": "node_id,created_at", "order": "created_at.desc", "limit": 100},
        )
    except Exception:
        return {}
    times = {}
    for row in rows:
        node_id = row.get("node_id")
        if node_id and node_id not in times:
            try:
                times[node_id] = time.mktime(
                    time.strptime(row["created_at"][:19], "%Y-%m-%dT%H:%M:%S")
                ) - time.timezone
            except (KeyError, ValueError):
                continue
    return times


def _clamped_limit(default=50, maximum=200):
    try:
        return max(1, min(int(request.args.get("limit", default)), maximum))
    except ValueError:
        return default


def _history_endpoint(table, optional_filters):
    """Shared shape of /events and /conversations: newest-first rows from Supabase."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return jsonify(error="supabase not configured on the brain"), 503
    params = {
        "select": "*",
        "order": "created_at.desc",
        "limit": _clamped_limit(),
    }
    for arg in optional_filters:
        value = request.args.get(arg)
        if value:
            params[arg] = f"eq.{value}"
    try:
        rows = _supabase_get(table, params)
    except Exception as e:
        return jsonify(error=f"supabase request failed: {e}"), 502
    return jsonify(**{table: rows})


@app.get("/events")
def events():
    """Recent events, newest first. Filters: ?limit=, ?event_type=, ?node_id=."""
    return _history_endpoint("events", ("event_type", "node_id"))


@app.get("/conversations")
def conversations():
    """Recent conversation lines, newest first. Filters: ?limit=, ?session_id=, ?node_id=."""
    return _history_endpoint("conversations", ("session_id", "node_id"))


APP_CHAT_NODE_ID = "app"  # distinguishes typed chats from voice sessions (node_id="leofric")


@app.post("/app/chat")
def app_chat():
    """Typed chat from the iOS app: mints/reuses a session_id, calls the
    brain, and persists both turns — unlike /chat, which the Pi calls and
    persists client-side itself. Persistence is best-effort: a Supabase
    hiccup must never cost the user their answer."""
    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify(error="missing 'message'"), 400
    history = data.get("history") or []
    session_id = data.get("session_id") or f"{APP_CHAT_NODE_ID}-{int(time.time() * 1000)}"

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "messages": messages, "stream": False, "keep_alive": -1},
            timeout=120,
        )
        resp.raise_for_status()
        reply = resp.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        return jsonify(error=f"ollama request failed: {e}"), 502

    if SUPABASE_URL and SUPABASE_KEY:
        for role, content in (("user", message), ("leofric", reply)):
            try:
                _supabase_post(
                    "conversations",
                    {"node_id": APP_CHAT_NODE_ID, "session_id": session_id,
                     "role": role, "content": content},
                )
            except Exception:
                pass  # best-effort — the user still gets their reply below

    return jsonify(response=reply, session_id=session_id)


if __name__ == "__main__":
    # threaded=True (Flask's default, made explicit): /feed holds a connection
    # open per viewer, which must not block /chat and /ingest.
    app.run(host="0.0.0.0", port=5000, threaded=True)
