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

- [x] **[CODE]** Pi POSTs person/identity events directly to the Mac
      (`POST /ingest/event/<node>`) alongside the existing Supabase logging
- [x] **[CODE]** Mac saves a snapshot JPEG per person-event to disk
      (`GET /snapshot/<id>`), with pruning so the disk never fills
- [x] **[CODE]** Pi stamps `session_id` on conversation rows (one wake-word
      session = one chat thread)
- [x] **[CODE]** Node roles in config (`security` / `assistant`) surfaced in `/nodes`

**2B COMPLETE (2026-07-10).** Verified on hardware end to end: Pi detects a
person → `brain/maclink.py` posts the event to the Mac → the Mac captures a
snapshot from the live frame stream and returns a `snapshot_id` → the Pi stores
that id in the event's Supabase `metadata` → `GET /snapshot/<id>` serves the
89 KB photo. `/nodes` reports `role: security` from the Pi's `X-Node-Role`
header; snapshots pruned oldest-first beyond `SNAPSHOT_KEEP` (2000). Wake-word
sessions rotate `session_id` after `SESSION_IDLE_SECONDS` idle (verified by unit
test; live voice check deferred to a spoken test before 2D). 8 tasks, all
TDD-reviewed; 25 unit tests across `macmini/test_server.py`, `tests/test_maclink.py`,
`tests/test_conversation.py`. Event push is best-effort — a dead Mac never stalls
the vision loop. Plan: `docs/superpowers/plans/2026-07-10-phase-2b-security-backend.md`.

---

### 2C — iOS App Core
**Goal:** A security camera in hand: app opens → live video in under 2 seconds.

- [x] **[CODE]** Propose Swift project structure for approval; scaffold Xcode project
      (SwiftUI, tab navigation, `LeofricAPI` network layer, Codable models
      matching the Mac's exact JSON)
- [x] **[CODE]** Live tab — custom MJPEG stream reader (~100 lines; AVPlayer
      can't play MJPEG), full-screen feed, node switcher
- [x] **[CODE]** Nodes tab — health board + settings (Mac base URL, preferences)
- [ ] **[YOU]** Build to your iPhone from Xcode on the Mac Mini, verify feed on device

**2C COMPLETE (2026-07-10).** SwiftUI app scaffolded via XcodeGen at
`ios/LeofricApp/`, zero third-party dependencies, builds/tests headlessly
against the iOS Simulator (`xcodebuild`). **Live tab verified showing a real,
current camera frame** pulled through the Mac's `/feed` from the Pi; Nodes tab
verified showing the `leofric` node online, role `security`, streaming.
14 unit tests across `LeofricAPITests`, `MJPEGStreamReaderTests`,
`AppSettingsTests`, `SmokeTests`.

**Critical bug found and fixed during live verification, not caught by unit
tests:** iOS's `URLSession` silently strips multipart boundary/header text
from `multipart/x-mixed-replace` responses before delegate callbacks ever see
it — confirmed by hex-dumping real bytes received (`ff d8 ff e0...`, JPEG's own
SOI/JFIF marker, never the `--leofricframe...` boundary text the original
parser was designed around). The Live tab was a permanent loading spinner
until this was found. Fixed by detecting frames via JPEG's own SOI/EOI markers
instead of multipart framing — see commit `d43145c` for the full root-cause
writeup. **Lesson for this codebase:** this class of bug (implementation
correct against synthetic unit-test fixtures, wrong against real platform
behavior) is exactly why live-device verification against the real Mac is a
required step before any networking task is called done, not an optional
nice-to-have — plan accordingly for 2D/2E.

Known accepted residual risk (documented in `MJPEGStreamReader.swift`, not a
blocker): SOI/EOI marker scanning doesn't walk JPEG marker-segment lengths, so
a `0xFF 0xD9` byte pair occurring inside table data (DHT/DQT) could in theory
truncate a frame early. Self-healing — the parser resyncs on the very next
real SOI — and low-probability given the Pi's standard `cv2.imencode` output.
Track as a fast-follow if ever observed in practice, not before.

Plan: `docs/superpowers/plans/2026-07-10-phase-2c-ios-app-core.md`.

---

### 2D — Alerts + Chats
**Goal:** The security timeline and the conversation surface.

- [x] **[CODE]** Alerts tab — event timeline with per-event snapshot thumbnails,
      filter by type; tap → full photo + "watch live"
- [x] **[CODE]** Chats tab — thread list (voice sessions auto-appear; compose for
      typed chats), iMessage-style thread view, ~2s polling while open
- [ ] **[YOU]** Test each screen on device; say "hey Jarvis…" and watch the
      thread appear in the app

**2D COMPLETE (2026-07-11).** Verified live against the real running Mac + Pi:
- **Alerts tab** renders the real security timeline — identity events labeled
  "Dane" with actual thumbnail photos pulled through the Mac's `/snapshot/<id>`,
  motion events correctly showing a fallback icon (no photo, by design), relative
  timestamps, newest-first, with a working type filter.
- **Chats tab** shows real threads — the "hey Jarvis" **voice sessions surface
  automatically** (grouped from Supabase by `session_id`, labeled "Voice session"),
  alongside typed chats; a fresh `/app/chat` message appeared as a "Typed chat"
  thread within seconds, proving the full write→read→group→render loop.
- New Mac endpoint `POST /app/chat` (mints/reuses `session_id`, persists both
  turns with `node_id="app"`, best-effort). New iOS: `LeofricStore` (shared API),
  `LeofricEvent`/`ConversationMessage`/`ConversationThread` models, `ImageCache`
  (NSCache thumbnails), Alerts + Chats tabs. 32 iOS unit tests + 8 new Mac tests.
- **Scope note:** Alerts filters by type only (not node) — one node exists today;
  `fetchEvents(nodeID:)` is ready for when Phase 4 adds a second node.
- Bugs caught in review and fixed before merge: `POST /app/chat` best-effort
  persistence; `AlertDetailView` infinite-spinner for no-photo events; and a
  Critical `ChatThreadView` message-ordering bug (the Mac returns conversations
  newest-first; the thread view was rendering bubbles reversed AND sending
  reversed history to the brain) plus a stale-poll overwrite race — both fixed.

Deferred UX polish (non-blocking, noted for a later pass): optimistic send +
surfaced error on send failure in `ChatThreadView`; the `#Preview` blocks in
`LiveFeedView`/`NodesView` need a `LeofricStore` env object to render in Xcode's
canvas (no runtime impact); a unit test for `sortedOldestFirst`/the poll guard.

Plan: `docs/superpowers/plans/2026-07-10-phase-2d-alerts-chats.md`.

---

### 2E — Push Notifications + Remote Access
**Goal:** Door opens in your house; phone buzzes in Arizona with a photo.

- [x] **[YOU]** Apple Developer account — confirmed (builder has shipped apps)
- [x] **[CODE]** APNs on the Mac (token auth via .p8 key): device registration
      endpoint (`POST /devices`), notification engine — identity-aware
      ("Dane at front door" vs "UNKNOWN PERSON"), per-node rules, ~60s cooldown,
      unknown persons always alert
- [x] **[CODE]** Rich notifications: snapshot photo attached (fetched over
      Tailscale; degrades to text-only if unreachable)
- [ ] **[YOU]** Install Tailscale on the Mac + iPhone (same account), set the app's
      base URL to the Tailscale hostname — see `docs/PHASE_2E_SETUP.md`
- [ ] **[YOU]** The Arizona test: leave home, trigger a person event, confirm
      notification + live feed work remotely — see `docs/PHASE_2E_SETUP.md`
- [ ] **[DECISION]** Phase 2 review. Is the app usable daily? Move to Phase 3 only when yes.

**2E CODE COMPLETE (2026-07-11), live delivery deferred to the builder's
on-device pass.** All push code is written, unit-tested, and deployed:
- Mac: `POST /devices` (file-backed token store), `macmini/notify.py` (identity-
  aware decision engine — 10 tests), `macmini/apns.py` (HTTP/2 + ES256 JWT sender,
  JWT signing verified against a throwaway key, payload/URL/headers verified vs the
  APNs spec — 6 tests), and a best-effort push hook in `/ingest/event` (fires on
  person/identity at a security node, never breaks ingest). Added `httpx[http2]` +
  `PyJWT[crypto]` (the only deps APNs allows; documented). Verified live: device
  registration works, bad tokens rejected, the hook safely no-ops while APNs is
  unconfigured.
- iOS: notification permission + remote registration + device-token POST
  (`PushRegistrar`/`AppDelegate`), and a **Notification Service Extension** that
  downloads the snapshot and attaches it (rich photo push). Both targets compile
  and the extension embeds; 34 unit tests.
- **What only the builder can do (real APNs delivery cannot be verified without
  it):** generate the `.p8` APNs key + configure the Mac, build to a physical
  iPhone and select the signing team, install Tailscale, and run the Arizona test.
  **Full step-by-step in `docs/PHASE_2E_SETUP.md`.**
- Review-caught fix: the Notification Service Extension's content handler is now
  idempotent (a slow snapshot download past the ~30s budget could otherwise have
  invoked it twice — undefined behavior over Tailscale/WAN).

Plan: `docs/superpowers/plans/2026-07-11-phase-2e-push-notifications.md`.

### On-device testing status (2026-07-11)
App built to the builder's physical iPhone and confirmed working on home WiFi:
**Live feed, Chats, and Alerts all verified on device.** Push notifications +
Tailscale (Stages C–D of the test plan) not yet run.

**⚠️ Event logging temporarily DISABLED (`EVENT_LOGGING_ENABLED=0` in the Pi's
`.env`).** On-device testing surfaced that continuous presence in frame logs an
identity/person event every few seconds, each capturing a snapshot — flooding
the Alerts tab and filling snapshot storage (127 MB of test clips accrued in one
session, since cleared). Turned off as a stopgap so it stops spamming; the live
feed and voice chat are unaffected (separate code paths). **This is temporary,
pending the smart-alerting work below.** To test push (Stage C) meanwhile,
trigger a manual event via `curl .../ingest/event/...` (see PHASE_2E_SETUP.md) —
that path bypasses the Pi flag — or set `EVENT_LOGGING_ENABLED=1` and restart.

---

## Phase 3 — Vision Intelligence Depth
**Goal:** System makes intelligent distinctions. Unknown person alert with image.
Identity expands beyond just the builder.

- [ ] **[CODE]** **Smart/debounced alerting (do this FIRST — it's why event
      logging is currently off).** One continuous presence should produce ONE
      alert, not one every few seconds; snapshot only on a new arrival or an
      unknown person, not on every frame-tick. Then re-enable `EVENT_LOGGING_ENABLED`.
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
