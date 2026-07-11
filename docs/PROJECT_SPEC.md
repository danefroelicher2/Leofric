# Leofric — Project Specification

## What Leofric Is

A home intelligence system — at its core, **a security camera system with a brain**,
not a chatbot with a camera. Physical nodes mounted in rooms watch and listen
continuously. A central brain on a Mac Mini coordinates everything. An iPhone app
gives the builder a live window into what Leofric sees, knows, and has flagged —
from anywhere in the world, over an encrypted private tunnel (Tailscale), with
nothing ever exposed to the public internet.

Each node has a **role**: a *security* node (e.g. pointed at the door) is
camera-first with instant person notifications; an *assistant* node (e.g. living
room) is mic-first for conversation. Same software, per-node configuration.

Leofric does not speak out loud. It watches, listens, thinks, and communicates through the app. This is intentional. Real intelligence systems do not announce themselves.

The winning moment the system is built around: a door opens, someone steps in,
and within a second or two the builder's phone — wherever it is — shows
*"UNKNOWN PERSON at front door"* with a snapshot photo, one tap from the live feed.

---

## Hardware

### Current Development Rig
- Raspberry Pi 5 8GB — edge compute node
- ReSpeaker XVF3000 — 4-mic array, USB, far-field audio input, AEC and noise suppression built in
- Logitech webcam — vision input
- UE Boom — optional single alert tone only, not voice output
- Mac Mini Apple Silicon M1, 8 GB RAM (Danes-Mac-mini-3.local, currently
  192.168.1.19) — always on, central brain, all heavy inference. The 8 GB is the
  known long-term scaling ceiling (bigger models, more nodes); fine through Phase 3.

### Development Environment
- Primary development machine: Windows PC
- Windows Terminal with SSH used to work on the Pi remotely
- Mac Mini used for heavy inference and eventually Xcode for iOS development
- iOS development (Xcode) requires Mac — Mac Mini fills this role when phase two begins

### Future Form Factor (not current priority)
- Single compact mountable unit per room
- Wide angle camera, small mic array integrated
- One power cable
- Corner mounted, angled downward

---

## What The System Does

### Vision
- Continuous camera feed from each node
- Motion detection — flags and logs all movement with timestamp
- Person detection — knows when a human is in frame
- Identity recognition — phase one is learning the builder, distinguishing him from unknown persons
- Phase two extends identity to additional known people
- Unknown person detected — sends alert to iPhone with short clip if feasible, still image as fallback

### Audio
- Always listening at low power for wake word
- Wake word detection uses **openWakeWord** (free, offline, no account). Original
  spec chose Porcupine/Picovoice, but the builder could not obtain a Picovoice
  account — see docs/DECISIONS.md ADR-003. Fully on-device, privacy preserved.
- Wake word is "hey Leofric" — custom model trained via openWakeWord's notebook
  (bring-up uses a pretrained model until the custom one is trained)
- Wake word activates full attention and conversation mode
- Builder speaks — audio transcribed locally on Pi — text sent to Mac Mini
- LLM processes on Mac Mini — response returns as text
- Response displays in app and in terminal — no voice output ever
- Sound anomaly detection is a future capability — not phase one

### Conversation and Memory
- Persistent conversation memory across sessions via Supabase
- Leofric knows its name, responds in conversation as Leofric
- Conversation history viewable in app

### Alerting
- Person detected at a security node — push notification with snapshot photo,
  identity-aware ("Dane at front door" vs "UNKNOWN PERSON at front door"),
  ~60s cooldown per node; unknown persons always alert
- Raw motion is logged and visible in the app's Alerts timeline but does not
  notify by itself (shadows and light changes are not visitors)
- All events logged with timestamp and node identifier; snapshots kept on the
  Mac with pruning

---

## The App — iOS First (design settled 2026-07-10)

- Built for iPhone, Apple ecosystem only for now; Android is a future consideration
  if this becomes a product. Builder has a developer account and has shipped iOS
  apps before.
- **Stack:** SwiftUI, iOS 17+, async/await, MVVM. One `LeofricAPI` client owns all
  endpoint calls; `Codable` models mirror the Mac API's exact JSON. **Zero
  third-party dependencies** — no supply-chain surface, matching the security posture.
- **Connectivity:** the app talks *only* to the Mac's API. At home that's the LAN;
  away it's the same request over Tailscale (mesh VPN, phone + Mac in one private
  network). The base URL lives in Settings, so home/away is configuration, not code.
- **Four tabs:**
  1. **Live** — opens straight to the security node, full-screen MJPEG
     (custom ~100-line stream reader; AVPlayer cannot play MJPEG). Target:
     app open → video in under 2 seconds. Swipe between nodes.
  2. **Alerts** — the security timeline: person/unknown/motion events, newest
     first, each with the snapshot photo taken at that moment; filter by node;
     tap → full photo + "watch live."
  3. **Chats** — thread list. Voice sessions appear automatically (each
     wake-word session = a thread; the builder's transcribed words as his
     messages, wake word stripped; Leofric's replies as responses). Compose
     button starts typed chats. ~2s polling while a thread is open (SSE is the
     later upgrade path; no websockets for MVP).
  4. **Nodes** — health board (online/offline, streaming, role, last seen,
     brain status) + app settings.
- **Push notifications** (APNs, token auth): identity-aware — "Dane at front
  door" quiet-ish, "UNKNOWN PERSON at front door" loud and always delivered;
  per-node rules; ~60s cooldown so one visit isn't thirty buzzes. Snapshot photo
  rides along (fetched from the Mac over Tailscale when the notification lands;
  degrades gracefully to text-only). Notifications travel via Apple's servers and
  work anywhere regardless of VPN state.
- **Explicitly not in scope:** a vision LLM. "What do you see" conversational
  vision was considered and deprioritized (8 GB M1 constraint + not the product's
  core). Leofric "sees" through the detection pipeline (motion → person →
  identity); the brain stays llama3.2, text-only. Live weather-type questions are
  a small future brain tool (the LLM has no internet), noted, not scheduled.

---

## The Central Brain — Mac Mini

- Always on at Danes-Mac-mini-3.local (currently 192.168.1.19)
- Flask API server already configured and running on port 5000 — do not rebuild
- Ollama already installed and running with Llama 3.2 — do not rebuild
- Both Flask server and Ollama auto-start on boot via LaunchAgents — already configured
- Supabase for persistent memory, event logs, identity data — needs fresh project setup
- Serves live feed and alert data to the iOS app
- Mac Mini infrastructure is set and forget — only touch it if something breaks

---

## The Build Phases

### Phase One — Core Loop (current focus)
One node. Motion detection working. Person detection working. Identity recognition learning the builder. Basic conversation via wake word with text response in terminal. All events logging to Mac Mini. This is the foundation everything else sits on. Do not advance until this phase is solid.

### Phase Two — App (current focus)
iOS app consuming live feed, alert notifications, conversation interface, node
status. Leofric moves from a terminal project to a product. Sub-phases (see
ROADMAP): 2A Mac API (done) → 2B security backend (events to the Mac, snapshots,
sessions, roles) → 2C app core (live feed first) → 2D alerts + chats →
2E push notifications + Tailscale ("the Arizona test"). Xcode 26.2 is installed
on the Mac Mini.

### Phase Three — Vision Intelligence Depth
Identity expanded to additional known people. Unknown person alert with clip. Anomaly detection begins. The system starts making intelligent distinctions rather than flagging everything.

### Phase Four — Second Node
Room to room presence handoff. Conversation context follows the builder between rooms. Distributed coordination between nodes. This is the distributed systems architecture story for interviews.

### Phase Five — Form Factor
Compact hardware replacing the development rig. Clean mount. Single cable. Looks like something that belongs on a wall.

---

## Current State — Read This First (updated 2026-07-11)

- **Phase 1 COMPLETE and hardened.** The Pi runs the full loop 24/7 under systemd
  (vision: motion → person → identity; audio: wake word → transcribe → brain →
  reply; everything logged to Supabase) and survives reboots. Reliability work
  done: persistent journald, hardware watchdog, EEPROM updated, active cooler
  installed, PMIC latch-off incident root-caused (see docs/MAC_STATUS.md).
- **ALL of Phase 2 CODE COMPLETE (2A–2E), on `main`.** Mac API (2A) +
  security backend/snapshots (2B) + the SwiftUI iOS app `ios/LeofricApp/` (2C
  Live/Nodes, 2D Alerts/Chats) + push notifications & the Notification Service
  Extension (2E) are all built and unit-tested. Live/Chats/Alerts confirmed on the
  builder's physical iPhone. See docs/ROADMAP.md for per-sub-phase detail and the
  executed plans in `docs/superpowers/plans/`.
- Mac Mini brain: reboot-proof (reboot test passed), model pinned resident
  (`keep_alive:-1`), reachable at `Danes-Mac-mini-3.local:5000` — hostname, not
  IP, is canonical. Do not rebuild; only extend.
- Supabase: live (`events` + `conversations`, RLS on); managed via the Supabase
  connector, service key on the Pi only.
- Wake word: **openWakeWord**, pretrained "hey Jarvis" until the custom
  "hey Leofric" model is trained (free Colab; one-file swap — see DECISIONS ADR-003).
- Next: on-device testing — push notifications (Stage C) + Tailscale/remote
  (Stage D) per **docs/PHASE_2E_SETUP.md**, then the Phase 2 review gate, then
  Phase 3 (smart alerting first — see ADR-008). Event logging is temporarily off.
- Prior project Mercia used a similar architecture — Leofric codebase is written entirely from scratch, do not reference or copy Mercia code

---

## What This Is Not

- Not a cloud-dependent system — everything runs locally, privacy is a feature
- Not a voice assistant in the Alexa or Siri sense — Leofric does not speak out loud
- Not a toy or demo — it runs in the home and is used daily
- Not finished at any single phase — it grows continuously

---

## Notes for Claude Code

- All code is written from scratch — Python on the Pi and Mac, Swift/SwiftUI in
  the app — clean, well-structured, defensible in a technical interview
- Every architectural decision should be explainable in plain English — no magic, no black boxes
- When in doubt, build the simpler thing first and make it work completely before adding complexity
- The builder is transitioning into Python mastery — write code that teaches as well as functions, with clear naming and comments that explain why not just what
- The bar for every decision is whether an engineer at Anduril or Leidos would find it serious and well-reasoned
- Phase two is the current focus — build it in the ROADMAP's sub-phase order so
  every stage leaves something usable; do not architect for phases three through
  five beyond what the design already accounts for
- Propose folder structure before writing any code and wait for confirmation
