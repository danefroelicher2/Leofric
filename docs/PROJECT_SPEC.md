# Leofric — Project Specification

## What Leofric Is

A home intelligence system. Physical nodes mounted in rooms watch and listen continuously. A central brain on a Mac Mini coordinates everything. An iPhone app gives the builder a live window into what Leofric sees, knows, and has flagged — from anywhere.

Leofric does not speak out loud. It watches, listens, thinks, and communicates through the app. This is intentional. Real intelligence systems do not announce themselves.

---

## Hardware

### Current Development Rig
- Raspberry Pi 5 8GB — edge compute node
- ReSpeaker XVF3000 — 4-mic array, USB, far-field audio input, AEC and noise suppression built in
- Logitech webcam — vision input
- UE Boom — optional single alert tone only, not voice output
- Mac Mini Apple Silicon (192.168.1.46) — always on, central brain, all heavy inference
- Fresh SD card — Raspberry Pi OS 64-bit, not yet flashed or configured

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
- Wake word detection uses Porcupine from Picovoice — not openWakeWord
- Wake word is "hey Leofric" — custom keyword trained via Porcupine web interface
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
- Motion detected while builder is away — push notification to iPhone
- Unknown person in frame — push notification with image or short clip
- All events logged with timestamp and node identifier

---

## The App — iOS First

- Built for iPhone, Apple ecosystem only for now
- Android is a future consideration if this becomes a product
- Builder has shipped two prior iOS apps — App Store Connect process is familiar
- Core screens:
  - Live camera feed, selectable by node
  - Alert feed with timestamps and thumbnails
  - Conversation interface — type or speak to Leofric, response appears as text
  - Node status — which nodes are active, last seen timestamp
- Push notifications for motion and unknown person events

---

## The Central Brain — Mac Mini

- Always on at 192.168.1.46
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

### Phase Two — App
iOS app consuming live feed, alert notifications, conversation interface, node status. Leofric moves from a terminal project to a product. Requires Xcode on Mac Mini.

### Phase Three — Vision Intelligence Depth
Identity expanded to additional known people. Unknown person alert with clip. Anomaly detection begins. The system starts making intelligent distinctions rather than flagging everything.

### Phase Four — Second Node
Room to room presence handoff. Conversation context follows the builder between rooms. Distributed coordination between nodes. This is the distributed systems architecture story for interviews.

### Phase Five — Form Factor
Compact hardware replacing the development rig. Clean mount. Single cable. Looks like something that belongs on a wall.

---

## Current State — Read This First

- Mac Mini Flask server: already configured, auto-starts on boot, do not rebuild
- Mac Mini Ollama: already configured, Llama 3.2 downloaded, auto-starts on boot, do not rebuild
- Mac Mini IP: 192.168.1.46, Flask on port 5000
- Raspberry Pi: fresh SD card, not yet flashed or configured — Pi setup is the first task before any deployment
- Supabase: needs a fresh project created — not yet configured for Leofric
- Wake word: Porcupine from Picovoice — custom keyword, do not use openWakeWord
- Prior project Mercia used a similar architecture — Leofric codebase is written entirely from scratch, do not reference or copy Mercia code

---

## What This Is Not

- Not a cloud-dependent system — everything runs locally, privacy is a feature
- Not a voice assistant in the Alexa or Siri sense — Leofric does not speak out loud
- Not a toy or demo — it runs in the home and is used daily
- Not finished at any single phase — it grows continuously

---

## Notes for Claude Code

- All code is written from scratch in Python — clean, well-structured, defensible in a technical interview
- Every architectural decision should be explainable in plain English — no magic, no black boxes
- When in doubt, build the simpler thing first and make it work completely before adding complexity
- The builder is transitioning into Python mastery — write code that teaches as well as functions, with clear naming and comments that explain why not just what
- The bar for every decision is whether an engineer at Anduril or Leidos would find it serious and well-reasoned
- Phase one is the only current focus — do not architect for phases two through five until phase one is complete
- Propose folder structure before writing any code and wait for confirmation
