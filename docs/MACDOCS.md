# Leofric — Mac Mini Brain: Build & Handoff Spec

**Audience:** a Claude instance working directly on the Mac Mini.
**Goal:** stand up the "brain" — a local LLM (Ollama / Llama 3.2) behind a small
Flask API — so the Raspberry Pi node can send it transcribed speech and get text
replies. Everything runs on the LAN; nothing goes to the cloud.

When you finish, **write a short return document** (see the last section) recording
the final facts (the Mac's static IP, model name, anything you changed) and push it
to the repo so the Pi-side Claude can wire the Pi to match.

---

## 1. Context — where the Mac fits

Leofric is a home-intelligence system. Two machines:

- **Raspberry Pi 5** (`192.168.1.20`) — the sensing node. Camera + ReSpeaker mic.
  Already working: motion, person, and face-identity detection; offline wake word
  (openWakeWord) and local speech-to-text (faster-whisper); event logging to
  Supabase. When the wake word fires, the Pi transcribes what the user says and
  needs to send that text somewhere smart to get a reply.
- **Mac Mini (this machine)** — the **brain**. Runs the heavy LLM. Receives the
  Pi's transcribed text over HTTP, runs it through Llama 3.2, returns text.

The Pi stays light; the Mac does the inference. That division is the whole point.

---

## 2. The API contract — DO NOT CHANGE

The Pi already has client code written against this exact contract. Match it
precisely or the Pi breaks.

**Server:** Flask, listening on `0.0.0.0:5000` (must be reachable from the LAN,
not just localhost).

**`GET /`** — health check. Returns:
```json
{"status": "ok", "service": "leofric-brain", "model": "llama3.2"}
```

**`POST /chat`** — request body:
```json
{
  "message": "what is the weather like",
  "history": [
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "Hello."}
  ]
}
```
`history` may be empty. Response body:
```json
{"response": "I can't see outside, but I can check a forecast if you connect one."}
```
On error, return a non-200 with `{"error": "..."}`.

---

## 3. Definition of done (checklist)

- [ ] Ollama installed and running; `llama3.2` model pulled.
- [ ] Flask server (`server.py`, below) running, bound to `0.0.0.0:5000`.
- [ ] `curl http://localhost:5000/` returns the health JSON.
- [ ] `curl -X POST http://localhost:5000/chat -H 'Content-Type: application/json' -d '{"message":"say hello in 3 words"}'`
      returns a `{"response": "..."}` with real model text.
- [ ] Reachable from the Pi: from another machine on the LAN,
      `curl http://<mac-ip>:5000/` works (macOS firewall allows incoming :5000).
- [ ] Mac does **not** sleep (it must stay reachable 24/7).
- [ ] Ollama **and** the Flask server **auto-start on boot** (LaunchAgents).
- [ ] Mac has a **static / DHCP-reserved IP** so it stops drifting (it was expected
      at `192.168.1.46` but had drifted; pick a reserved address and record it).

---

## 4. The server code

Create `server.py` with exactly this (it is also in the repo at `macmini/server.py`,
and matches the Pi's client). Keep the routes and JSON shapes identical:

```python
import os
import requests
from flask import Flask, jsonify, request

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("LEOFRIC_MODEL", "llama3.2")

SYSTEM_PROMPT = (
    "You are Leofric, a local home intelligence system running on the builder's "
    "own hardware. You watch and listen through sensors and answer through text. "
    "You are concise, calm, and direct. Keep replies short unless asked for detail."
)

app = Flask(__name__)

@app.get("/")
def health():
    return jsonify(status="ok", service="leofric-brain", model=MODEL)

@app.post("/chat")
def chat():
    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []
    if not message:
        return jsonify(error="missing 'message'"), 400
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "messages": messages, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        reply = resp.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        return jsonify(error=f"ollama request failed: {e}"), 502
    return jsonify(response=reply)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

---

## 5. Build steps

```bash
# 1. Install Ollama (if missing)
#    Either the official installer from https://ollama.com/download,
#    or:  brew install ollama
ollama --version

# 2. Start Ollama and pull the model
ollama serve   # (or the menu-bar app); then in another shell:
ollama pull llama3.2
ollama list    # confirm llama3.2 is present

# 3. Python env for the Flask server (macOS ships python3)
mkdir -p ~/leofric-brain && cd ~/leofric-brain
# put server.py here (section 4)
python3 -m venv venv && source venv/bin/activate
pip install flask requests

# 4. Run it
python3 server.py
# In another shell, verify:
curl -s http://localhost:5000/ ; echo
curl -s -X POST http://localhost:5000/chat -H 'Content-Type: application/json' \
     -d '{"message":"say hello in exactly three words"}' ; echo
```

### Keep the Mac awake (required — a sleeping Mac is unreachable)
```bash
# Never sleep on AC power; keep disk + network up:
sudo pmset -c sleep 0 disksleep 0 womp 1
# (womp = wake on network. Verify with: pmset -g)
```

### Firewall (if macOS Application Firewall is on)
Allow incoming connections for `python3` (System Settings → Network → Firewall →
Options), or the Pi will get connection-refused on `:5000`.

### Auto-start on boot (LaunchAgents)
Create two LaunchAgents so Ollama and the Flask server start on login/boot and
restart if they crash. Suggested:
- `~/Library/LaunchAgents/com.leofric.ollama.plist` → runs `ollama serve`
  (skip if the Ollama app already launches at login).
- `~/Library/LaunchAgents/com.leofric.brain.plist` → runs the venv's python on
  `server.py`, with `KeepAlive` and `RunAtLoad` true.
Load with `launchctl load -w <plist>` and verify a reboot brings both back.

### Static / reserved IP
Reserve this Mac's IP in the router's DHCP settings (bind it to the Mac's Wi-Fi
MAC address), or set a manual IP in System Settings → Network. **Record the final
IP** — the Pi needs it.

---

## 6. Verify end-to-end
From any other machine on the LAN (not the Mac):
```bash
curl -s http://<mac-ip>:5000/ ; echo
curl -s -X POST http://<mac-ip>:5000/chat -H 'Content-Type: application/json' \
     -d '{"message":"who are you?"}' ; echo
```
Expect the health JSON, then a short first-person reply as "Leofric".

---

## 7. Return document (write this before you hand back)

Create `docs/MAC_STATUS.md` in the repo and push it, containing:
- **Final Mac IP** (static/reserved) and how it was set.
- **Model** actually used (e.g. `llama3.2`, or a size variant like `llama3.2:3b`).
- **Confirmation** the API contract in section 2 is served exactly as written
  (paste the two working `curl` outputs).
- **Auto-start**: which LaunchAgents were installed, and that a reboot test passed.
- **Sleep**: confirm `pmset -g` shows sleep disabled on AC.
- **Firewall**: whether it was on and what was allowed.
- **Anything you changed or deviated from** in this spec, and why.

The Pi-side Claude will read that file, set the Pi's `MAC_MINI_URL` to your IP,
and run a live conversation to close Phase 1J.

---

## 8. Out of scope for now (Phase 2 — do NOT build yet)
Later the Mac will also serve the iOS app: `GET /events`, `GET /feed` (MJPEG),
`GET /conversations`, `GET /nodes`, and push notifications. Ignore these for now.
Phase 1J is only the `/chat` brain. Keep it minimal and solid.
