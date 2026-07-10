# Leofric — Build Roadmap

## How To Read This

Each phase has numbered steps. Steps marked **[CODE]** are written by Claude. Steps marked
**[YOU]** require physical action, account creation, or hardware. Steps marked **[DECISION]**
are points where we pause to evaluate and choose direction before continuing.

Current position is marked with `← YOU ARE HERE`.

---

## Phase 0 — Infrastructure
**Goal:** Pi is reachable over SSH and ready for development.
**Status: COMPLETE**

- [x] Flash Pi OS Bookworm Lite to SD card via Pi Imager
- [x] Fix Pi Imager cloud-init bug (missing ssh-keygen in user-data) — see PI_IMAGER_SSH_FIX.md
- [x] SSH working: `ssh dane@leofric.local`
- [x] Hostname: `leofric`, User: `dane`, WiFi: connected
- [x] Active cooler ordered (arrives in a few days — install when received)

---

## Phase 1 — Core Loop
**Goal:** One node. Camera watching. Mic listening. Wake word triggers conversation.
Motion and person events log to Mac Mini. Identity learns the builder. Everything
runs as a stable, always-on process.

---

### 1A — Hardware Verification
**Goal:** Confirm webcam and ReSpeaker are detected and functional on the Pi.

- [x] **[YOU]** Plug Logitech webcam into Pi USB port
- [x] **[YOU]** Plug ReSpeaker XVF3000 into Pi USB port
- [x] **[CODE]** Run hardware check script — confirms camera device exists, confirms mic
      device exists, captures a test frame, records a 3-second audio clip
- [x] **[YOU]** Verify test frame looks correct, test audio clip plays back

**1A COMPLETE.** Camera = Logitech BRIO Ultra HD at `/dev/video0`. Mic = ReSpeaker
4 Mic Array at ALSA `card 2`. Both capture confirmed (720p frame + 3s clip verified).

---

### 1B — Project Structure
**Goal:** Clean Python project layout on the Pi before any feature code is written.

- [x] **[CODE]** Propose folder structure for approval
- [x] **[YOU]** Confirm or adjust the structure
- [x] **[CODE]** Create folders, `requirements.txt`, `README`, Python virtual environment setup
- [x] **[CODE]** Push initial project skeleton to GitHub

**1B COMPLETE.** Repo cloned to `/home/dane/leofric` on the Pi via a read-only
GitHub deploy key. venv at `~/leofric/venv`. Workflow: develop on Windows → push →
`git pull` on the Pi → run/test on hardware.

Proposed structure (subject to your approval):
```
leofric/
├── main.py               # entry point — starts all subsystems
├── config.py             # all constants and settings in one place
├── requirements.txt
├── vision/
│   ├── camera.py         # camera feed management
│   ├── motion.py         # motion detection
│   ├── person.py         # person detection
│   └── identity.py       # face recognition and identity
├── audio/
│   ├── microphone.py     # mic input from ReSpeaker
│   ├── wakeword.py       # Porcupine wake word listener
│   └── transcription.py  # Whisper speech-to-text
├── brain/
│   ├── client.py         # HTTP client talking to Mac Mini Flask API
│   └── conversation.py   # conversation state and memory
├── storage/
│   └── events.py         # Supabase event logging
└── logs/                 # runtime logs
```

---

### 1C — Camera Pipeline
**Goal:** Stable continuous camera feed with frame access for downstream processing.

- [x] **[CODE]** `vision/camera.py` — opens camera device, reads frames in a loop,
      exposes latest frame to other modules via thread-safe access
- [x] **[CODE]** Test script — display camera stats, save sample frame to disk
- [x] **[YOU]** Confirm frame captures correctly over SSH (view saved image)

**1C COMPLETE.** Threaded capture at 1280x720. Driver negotiates ~15fps under
auto-exposure, which is ample for the detectors. Sample frame verified clean.

---

### 1D — Motion Detection
**Goal:** Detect when something moves in frame. Log every motion event with timestamp.

- [x] **[CODE]** `vision/motion.py` — background subtraction (OpenCV MOG2),
      motion threshold tuning, outputs True/False per frame with bounding box
- [x] **[CODE]** Motion events written to local log file with timestamp
- [x] **[YOU]** Walk in front of camera, confirm motion is detected in logs

**1D COMPLETE.** MOG2 detector fires on movement, quiet when still, boxes track
the mover. Events logged to `logs/leofric.log` with rising/falling-edge debounce.

---

### 1E — Person Detection
**Goal:** Distinguish a person from other motion (shadow, light change, animal, object).

- [x] **[CODE]** `vision/person.py` — person detector, runs on frames where motion
      is detected (not every frame — saves CPU)
- [x] **[CODE]** Person detection events logged separately from raw motion events
- [x] **[YOU]** Walk in front of camera, confirm person vs no-person is correctly classified

**1E COMPLETE.** Swapped HOG for a MobileNet-SSD DNN (via OpenCV's dnn module,
no new deps) because the deployment target sees seated/partial/multiple bodies
that HOG can't handle. Detected the builder seated at 0.97 confidence. Model
fetched by `scripts/fetch_models.py` into `data/models/`.

---

### 1F — Identity Recognition
**Goal:** Pi learns what you look like. Knows the difference between you and an unknown person.

- [x] **[CODE]** `vision/identity.py` — face detection + encoding using OpenCV YuNet
      (detect) + SFace (128-d embeddings); loads known encodings from disk
- [x] **[CODE]** Enrollment script — captures 25 face samples from the live camera,
      saves embeddings to `data/known_faces.npz`
- [x] **[YOU]** Run enrollment
- [x] **[CODE]** Identity classification: outputs builder name or "unknown" per face
- [x] **[DECISION]** Recognition accuracy evaluated — builder matched at 0.80 cosine
      vs a 0.363 threshold (>2x margin). Solid; no tuning needed.

**1F COMPLETE.** Chose OpenCV YuNet+SFace over dlib/face_recognition to avoid a
slow, fragile Pi compile. This completes the entire vision pipeline (1C–1F).

---

### 1G — Supabase Setup
**Goal:** Persistent event log and conversation history in the cloud.

- [x] **[YOU]** Create free Supabase account at supabase.com
- [x] **[YOU]** Create new project named "leofric"
- [x] **[YOU]** Paste project URL and service_role key into `.env` on the Pi
- [x] **[CODE]** `storage/events.py` — Supabase client, events + conversations tables
- [x] **[CODE]** Create the tables via migration (done through the Supabase connector)
- [x] **[CODE]** Test: wrote a dummy event, verified in the cloud, then cleaned up

**1G COMPLETE.** Project ref `ylefaaoyjcikcdoqnqvy`, us-east-2. Pi writes with the
service_role key (in `.env`); RLS on all tables. Security advisors reviewed and the
auto-RLS function's public EXECUTE revoked. DB managed directly via the Supabase
connector — no manual dashboard SQL.

---

### 1H — Audio Pipeline
**Goal:** ReSpeaker always listening at low power, ready to activate on wake word.

**NOTE:** Wake word switched from Porcupine/Picovoice to **openWakeWord** — the
builder could not obtain a Picovoice account. Free, offline, no account. See
docs/DECISIONS.md ADR-003.

- [x] **[CODE]** `audio/microphone.py` — opens ReSpeaker (16kHz mono) via PyAudio,
      fixed-size frames
- [x] **[CODE]** `audio/wakeword.py` — openWakeWord listener on mic stream,
      fires when the wake word is detected
- [x] **[YOU]** Bring-up test with a pretrained model — confirmed, 0.90–0.99 scores
- [ ] **[CODE/YOU]** Train custom "Hey Leofric" model (free openWakeWord Colab),
      drop `hey_leofric.onnx` into `data/models/`, retest (code auto-picks it up)

**1H audio pipeline PROVEN** with the pretrained model. Only the custom "Hey
Leofric" model remains — a one-file swap; the wake phrase is "Hey Jarvis" until
then.

---

### 1I — Transcription
**Goal:** When wake word fires, capture what follows and convert to text.

- [x] **[CODE]** `audio/transcription.py` — on wake word, records until silence
      (energy-based endpointing), transcribes locally with faster-whisper
- [x] **[YOU]** Confirmed: full sentences transcribe correctly (e.g. "what is the
      weather today"), ~2s latency on the Pi
- [x] **[DECISION]** Keeping `base` — accuracy good, ~2s per utterance. `small` is
      a one-line config bump if ever needed.

**1I COMPLETE.** Local speech-to-text via faster-whisper (ADR-004). Wake word →
record → transcribe → text works end to end.

---

### 1J — Mac Mini Integration
**Goal:** Pi sends conversation text to Mac Mini, Mac Mini runs LLM, response returns to Pi.

- [x] **[CODE]** `brain/client.py` — HTTP client POSTs transcribed text to the Mac
      Mini Flask API, receives LLM response text
- [x] **[CODE]** `brain/conversation.py` — maintains conversation history within a session
- [x] **[CODE]** Mac Mini brain built (it never existed — ADR-005) and verified from
      the Pi: typed conversation works, context carries across turns
- [x] **[YOU]** Confirmed via typed test; voice→brain path wired in 1K
- [ ] **[CODE]** Log conversation to Supabase conversations table (wired in main.py, 1K)

**1J COMPLETE.** Pi ↔ Mac brain works over the drift-proof hostname
`Danes-Mac-mini-3.local:5000` (llama3.2). See docs/MAC_STATUS.md.

---

### 1K — Core Loop Integration
**Goal:** All subsystems running together as a single always-on process.

- [x] **[CODE]** `main.py` — starts all subsystems in threads, coordinates between them:
      camera thread → motion/person/identity pipeline,
      audio thread → wake word → transcription → Mac Mini → log
- [x] **[CODE]** Graceful shutdown handling (Ctrl+C, systemd stop)
- [x] **[CODE]** `systemd` service file so Leofric auto-starts on Pi boot
- [x] **[YOU]** Reboot Pi, confirm Leofric starts automatically — **PASSED**
- [x] **[YOU]** Run for 30+ minutes, confirm no crashes, check logs
- [x] **[DECISION]** Phase 1 review — PASSED. Core loop stable, identity solid
      (`dane` 0.56–0.75), conversation responsive (~3s, coherent). Cleared to Phase 2.

**1K COMPLETE (2026-07-06).** `main.py` runs as a systemd service (`enabled` +
`active (running)`). Reboot test passed: power-cycled the Pi, Leofric auto-started
in ~30s with nobody logged in — sensing, recognizing the builder, logging to
Supabase. Full voice loop verified **headless**: "Hey Jarvis" → transcribe → Mac
brain → coherent reply, all from the background service. Also hardened
transcription with faster-whisper `vad_filter=True` to stop hallucination on
marginal audio (see CLAUDE.md). **PHASE 1 IS DONE — next is Phase 2 (iOS app).**

`← YOU ARE HERE` → Phase 2B (security backend), then 2C (iOS app core).

---

## Phase 2 — iOS App
**Goal:** iPhone app showing live feed, alert notifications, conversation interface,
node status. Leofric moves from a terminal project to a product.

---

### 2A — Mac Mini API Expansion
**Goal:** Mac Mini Flask API serves data the app needs.

- [x] **[CODE]** New endpoints on Mac Mini:
      - `GET /events` — recent events with timestamps and type
      - `GET /feed` — MJPEG live camera stream from Pi
      - `GET /conversations` — recent conversation history
      - `GET /nodes` — node status (online/offline, last seen)
      - `POST /chat` — send message, get response (existing endpoint)
- [x] **[CODE]** Pi streams camera frames to Mac Mini via HTTP

**2A COMPLETE (2026-07-10).** Events/conversations proxied from Supabase; Pi
pushes ~4 JPEG fps (`vision/streamer.py`) to `POST /ingest/frame/<node>`, kept
in memory only and re-broadcast as MJPEG at `/feed`. Verified on hardware: live
room frame captured through the Mac's `/feed`, `/nodes` shows `leofric`
online+streaming. 11 unit tests in `macmini/test_server.py`.

---

> **Phase 2 design decided 2026-07-10 (brainstormed on the Mac).** The app is a
> **security camera system with a brain** — not a chatbot with a camera. Priority:
> (1) live feed + instant identity-aware person notifications with snapshot photos,
> (2) chats (voice sessions surface in the app as threads; typed chats from
> anywhere), (3) per-node roles ("security" vs "assistant"). Remote access is
> **Tailscale-only** (encrypted mesh VPN; nothing exposed to the public internet)
> — the phone talks solely to the Mac API, from home or Arizona alike. No vision
> LLM: "seeing" = the existing detection pipeline; llama3.2 stays the brain.
> SwiftUI, iOS 17+, async/await, zero third-party dependencies. Full design in
> PROJECT_SPEC ("The App").

### 2B — Security Backend (Mac + Pi)
**Goal:** The Mac can react to a person at the door in under a second.

- [ ] **[CODE]** Pi POSTs person/identity events directly to the Mac
      (`POST /ingest/event/<node>`) alongside the existing Supabase logging
- [ ] **[CODE]** Mac saves a snapshot JPEG per person-event to disk
      (`GET /snapshot/<event_id>`), with pruning so the disk never fills
- [ ] **[CODE]** Pi stamps `session_id` on conversation rows (one wake-word
      session = one chat thread)
- [ ] **[CODE]** Node roles in config (`security` / `assistant`) surfaced in `/nodes`

---

### 2C — iOS App Core
**Goal:** A security camera in hand: app opens → live video in under 2 seconds.

- [ ] **[CODE]** Propose Swift project structure for approval; scaffold Xcode project
      (SwiftUI, tab navigation, `LeofricAPI` network layer, Codable models
      matching the Mac's exact JSON)
- [ ] **[CODE]** Live tab — custom MJPEG stream reader (~100 lines; AVPlayer
      can't play MJPEG), full-screen feed, node switcher
- [ ] **[CODE]** Nodes tab — health board + settings (Mac base URL, preferences)
- [ ] **[YOU]** Build to your iPhone from Xcode on the Mac Mini, verify feed on device

---

### 2D — Alerts + Chats
**Goal:** The security timeline and the conversation surface.

- [ ] **[CODE]** Alerts tab — event timeline with per-event snapshot thumbnails,
      filter by node/type; tap → full photo + "watch live"
- [ ] **[CODE]** Chats tab — thread list (voice sessions auto-appear; compose for
      typed chats), iMessage-style thread view, ~2s polling while open
- [ ] **[YOU]** Test each screen on device; say "hey Jarvis…" and watch the
      thread appear in the app

---

### 2E — Push Notifications + Remote Access
**Goal:** Door opens in your house; phone buzzes in Arizona with a photo.

- [x] **[YOU]** Apple Developer account — confirmed (builder has shipped apps)
- [ ] **[CODE]** APNs on the Mac (token auth via .p8 key): device registration
      endpoint (`POST /devices`), notification engine — identity-aware
      ("Dane at front door" vs "UNKNOWN PERSON"), per-node rules, ~60s cooldown,
      unknown persons always alert
- [ ] **[CODE]** Rich notifications: snapshot photo attached (fetched over
      Tailscale; degrades to text-only if unreachable)
- [ ] **[YOU]** Install Tailscale on the Mac + iPhone (same account), set the app's
      base URL to the Tailscale hostname
- [ ] **[YOU]** The Arizona test: leave home, trigger a person event, confirm
      notification + live feed work remotely
- [ ] **[DECISION]** Phase 2 review. Is the app usable daily? Move to Phase 3 only when yes.

---

## Phase 3 — Vision Intelligence Depth
**Goal:** System makes intelligent distinctions. Unknown person alert with image.
Identity expands beyond just the builder.

- [ ] **[CODE]** Unknown person triggers push notification with still image attached
- [ ] **[CODE]** Identity enrollment expanded — add additional known people
- [ ] **[CODE]** Short clip capture on unknown person detection (10-second buffer, save on trigger)
- [ ] **[CODE]** Clip or image attached to alert notification
- [ ] **[DECISION]** Sound anomaly detection scoped here — evaluate whether to tackle
      it in Phase 3 or defer to Phase 4.

---

## Phase 4 — Second Node
**Goal:** Second Pi in a second room. Presence handoff between rooms.
Distributed coordination. This is the architecture story.

- [ ] **[YOU]** Acquire second Pi 5 8GB + accessories
- [ ] **[CODE]** Node registration system on Mac Mini — nodes announce themselves
- [ ] **[CODE]** Presence tracking — system knows which room the builder is in based
      on which node last saw them
- [ ] **[CODE]** Conversation context follows the builder between rooms
- [ ] **[CODE]** App updated — node selector on live feed, multi-node alert feed
- [ ] **[DECISION]** Phase 4 review. Is the handoff seamless? Evaluate latency.

---

## Phase 5 — Form Factor
**Goal:** Replace development rig with compact, mountable hardware. Clean install.
One power cable. Looks like it belongs on a wall.

- [ ] **[DECISION]** Hardware selection — evaluate compact Pi 5 cases, wide-angle cameras,
      integrated mic arrays vs current hardware at this stage
- [ ] **[CODE]** Any driver or config changes required by new hardware
- [ ] **[YOU]** Physical installation in each room
- [ ] Final system review — is this something you would show someone?

---

## Mac Mini — Do Not Touch

- IP: `192.168.1.19` (DHCP-assigned, not reserved — see docs/MAC_STATUS.md)
- Flask API: port 5000, auto-starts on boot
- Ollama: Llama 3.2, auto-starts on boot
- Do not rebuild, do not modify config — only add new endpoints

---

## Key Accounts Needed (Acquire Before Phase 1G/1H)

| Service | When Needed | Cost | Purpose |
|---|---|---|---|
| ~~Picovoice~~ | ~~Phase 1H~~ | — | Dropped — replaced by openWakeWord (no account). See DECISIONS.md ADR-003 |
| Supabase | Phase 1G | Free tier | Event log, conversation history |
| Apple Developer | Phase 2D | $99/year | Push notifications |

Wake word (openWakeWord) needs no account. Training a custom "Hey Leofric" model
uses a free Google Colab notebook (Google account, which the builder already has).
