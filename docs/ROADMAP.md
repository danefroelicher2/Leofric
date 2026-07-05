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

- [ ] **[CODE]** `vision/camera.py` — opens camera device, reads frames in a loop,
      exposes latest frame to other modules via thread-safe access
- [ ] **[CODE]** Test script — display camera stats, save sample frame to disk
- [ ] **[YOU]** Confirm frame captures correctly over SSH (view saved image)

---

### 1D — Motion Detection
**Goal:** Detect when something moves in frame. Log every motion event with timestamp.

- [ ] **[CODE]** `vision/motion.py` — background subtraction (OpenCV MOG2),
      motion threshold tuning, outputs True/False per frame with bounding box
- [ ] **[CODE]** Motion events written to local log file with timestamp
- [ ] **[YOU]** Walk in front of camera, confirm motion is detected in logs

---

### 1E — Person Detection
**Goal:** Distinguish a person from other motion (shadow, light change, animal, object).

- [ ] **[CODE]** `vision/person.py` — HOG person detector via OpenCV,
      runs on frames where motion is detected (not every frame — saves CPU)
- [ ] **[CODE]** Person detection events logged separately from raw motion events
- [ ] **[YOU]** Walk in front of camera, confirm person vs no-person is correctly classified

---

### 1F — Identity Recognition
**Goal:** Pi learns what you look like. Knows the difference between you and an unknown person.

- [ ] **[CODE]** `vision/identity.py` — face detection and encoding using face_recognition
      library (built on dlib), loads known encodings from disk
- [ ] **[CODE]** Enrollment script — captures 20+ face images of you from the live camera,
      generates and saves encodings to disk
- [ ] **[YOU]** Run enrollment: sit in front of camera for ~60 seconds while it captures
- [ ] **[CODE]** Identity classification runs on frames where a person is detected:
      outputs "builder", "unknown", or "no face"
- [ ] **[DECISION]** Evaluate recognition accuracy before proceeding. Tune if needed.

---

### 1G — Supabase Setup
**Goal:** Persistent event log and conversation history in the cloud.

- [ ] **[YOU]** Create free Supabase account at supabase.com
- [ ] **[YOU]** Create new project named "leofric"
- [ ] **[YOU]** Paste project URL and anon key into config — Claude will tell you exactly
      where to put them
- [ ] **[CODE]** `storage/events.py` — Supabase client, schema for events table
      (timestamp, node_id, event_type, metadata), schema for conversations table
- [ ] **[CODE]** Create the tables via migration script
- [ ] **[CODE]** Test: write a dummy event, confirm it appears in Supabase dashboard

---

### 1H — Audio Pipeline
**Goal:** ReSpeaker always listening at low power, ready to activate on wake word.

- [ ] **[YOU]** Create free Picovoice account at picovoice.ai
- [ ] **[YOU]** Generate access key (free tier supports one device)
- [ ] **[YOU]** Paste access key into config
- [ ] **[CODE]** `audio/microphone.py` — opens ReSpeaker device via PyAudio,
      continuous audio stream, thread-safe frame buffer
- [ ] **[CODE]** `audio/wakeword.py` — Porcupine listener on mic stream,
      fires callback when "hey Leofric" is detected
- [ ] **[YOU]** Say "hey Leofric" — confirm wake word triggers in logs

---

### 1I — Transcription
**Goal:** When wake word fires, capture what follows and convert to text.

- [ ] **[CODE]** `audio/transcription.py` — on wake word, records until silence
      (voice activity detection), sends audio to Whisper (local, runs on Pi),
      returns transcribed text
- [ ] **[YOU]** Say "hey Leofric, what time is it" — confirm text appears correctly in logs
- [ ] **[DECISION]** Evaluate Whisper model size vs accuracy vs speed on Pi 5.
      Start with `base` model. Move to `small` if accuracy is poor.

---

### 1J — Mac Mini Integration
**Goal:** Pi sends conversation text to Mac Mini, Mac Mini runs LLM, response returns to Pi.

- [ ] **[CODE]** `brain/client.py` — HTTP client that POSTs transcribed text to
      Mac Mini Flask API at 192.168.1.46:5000, receives LLM response text
- [ ] **[CODE]** `brain/conversation.py` — maintains conversation history,
      prepends context to each request so Leofric has memory within a session
- [ ] **[CODE]** Verify Mac Mini Flask API endpoint exists and accepts requests
      (do not modify the Mac Mini setup — only verify it works)
- [ ] **[YOU]** Say "hey Leofric" followed by a question — confirm response
      text appears in terminal
- [ ] **[CODE]** Log conversation to Supabase conversations table

---

### 1K — Core Loop Integration
**Goal:** All subsystems running together as a single always-on process.

- [ ] **[CODE]** `main.py` — starts all subsystems in threads, coordinates between them:
      camera thread → motion/person/identity pipeline,
      audio thread → wake word → transcription → Mac Mini → log
- [ ] **[CODE]** Graceful shutdown handling (Ctrl+C, systemd stop)
- [ ] **[CODE]** `systemd` service file so Leofric auto-starts on Pi boot
- [ ] **[YOU]** Reboot Pi, confirm Leofric starts automatically
- [ ] **[YOU]** Run for 30+ minutes, confirm no crashes, check logs
- [ ] **[DECISION]** Phase 1 review. Is the core loop stable? Does identity work well
      enough? Is conversation responsive? Only move to Phase 2 when all three are solid.

---

## Phase 2 — iOS App
**Goal:** iPhone app showing live feed, alert notifications, conversation interface,
node status. Leofric moves from a terminal project to a product.

---

### 2A — Mac Mini API Expansion
**Goal:** Mac Mini Flask API serves data the app needs.

- [ ] **[CODE]** New endpoints on Mac Mini:
      - `GET /events` — recent events with timestamps and type
      - `GET /feed` — MJPEG live camera stream from Pi
      - `GET /conversations` — recent conversation history
      - `GET /nodes` — node status (online/offline, last seen)
      - `POST /chat` — send message, get response (existing endpoint)
- [ ] **[CODE]** Pi streams camera frames to Mac Mini via HTTP

---

### 2B — iOS App Structure
**Goal:** Clean Swift project with navigation and data layer.

- [ ] **[CODE]** Propose Swift project structure for approval
- [ ] **[YOU]** Confirm structure
- [ ] **[CODE]** Xcode project scaffolding — tab navigation, network layer,
      models matching API responses
- [ ] **[YOU]** Open project in Xcode on Mac Mini, build to your iPhone

---

### 2C — Core Screens
**Goal:** Four screens working end to end.

- [ ] **[CODE]** Live feed screen — MJPEG stream from Mac Mini
- [ ] **[CODE]** Alert feed screen — list of motion/person/unknown events with timestamps
- [ ] **[CODE]** Conversation screen — chat interface, sends to Mac Mini, displays response
- [ ] **[CODE]** Node status screen — shows leofric node online/offline, last seen
- [ ] **[YOU]** Test each screen on device

---

### 2D — Push Notifications
**Goal:** Motion while away triggers notification to iPhone.

- [ ] **[YOU]** Apple Developer account required ($99/year) — confirm you have one
- [ ] **[CODE]** APNs integration on Mac Mini — sends push when Pi logs a person event
- [ ] **[CODE]** Notification includes event type and timestamp
- [ ] **[YOU]** Leave home range, trigger motion, confirm notification arrives
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

- IP: `192.168.1.46`
- Flask API: port 5000, auto-starts on boot
- Ollama: Llama 3.2, auto-starts on boot
- Do not rebuild, do not modify config — only add new endpoints

---

## Key Accounts Needed (Acquire Before Phase 1G/1H)

| Service | When Needed | Cost | Purpose |
|---|---|---|---|
| Picovoice | Phase 1H | Free (1 device) | Wake word — "hey Leofric" |
| Supabase | Phase 1G | Free tier | Event log, conversation history |
| Apple Developer | Phase 2D | $99/year | Push notifications |
