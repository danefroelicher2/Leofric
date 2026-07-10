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

import os
import threading
import time

import requests
from flask import Flask, Response, jsonify, request


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
FEED_FPS = 4  # re-broadcast rate of /feed (matches the Pi's default push rate)
MAX_FRAME_BYTES = 5 * 1024 * 1024  # reject absurd uploads; 720p JPEG is ~100 KB

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
    jpeg = request.get_data()
    if not jpeg or len(jpeg) > MAX_FRAME_BYTES:
        return jsonify(error="expected a JPEG body under 5 MB"), 400
    if not jpeg.startswith(b"\xff\xd8"):  # JPEG magic — cheap sanity check
        return jsonify(error="body is not a JPEG"), 400
    with _frames_lock:
        _frames[node] = {"jpeg": jpeg, "at": time.time()}
    return jsonify(ok=True)


def _latest_frame(node):
    with _frames_lock:
        entry = _frames.get(node)
        return (entry["jpeg"], entry["at"]) if entry else (None, 0.0)


def _mjpeg_stream(node):
    """Yield the latest frame as multipart MJPEG until the client disconnects.

    Frames are re-sent at FEED_FPS even when unchanged so players that measure
    liveness by inter-frame gaps don't stall during quiet moments.
    """
    while True:
        jpeg, at = _latest_frame(node)
        if jpeg is not None:
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


@app.get("/nodes")
def nodes():
    now = time.time()
    with _frames_lock:
        seen = {n: e["at"] for n, e in _frames.items()}
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


if __name__ == "__main__":
    # threaded=True (Flask's default, made explicit): /feed holds a connection
    # open per viewer, which must not block /chat and /ingest.
    app.run(host="0.0.0.0", port=5000, threaded=True)
