# Leofric — Project Specification

## What Leofric Is

A home intelligence system. Physical nodes mounted in rooms watch and listen continuously. A central brain on a Mac Mini coordinates everything. An iPhone app gives the builder a live window into what Leofric sees, knows, and has flagged — from anywhere.

Leofric does not speak out loud. It watches, listens, thinks, and communicates through the app. This is intentional. Real intelligence systems do not announce themselves.

---

## Hardware

### Current Development Rig
- Raspberry Pi 5 8GB — edge compute node
- ReSpeaker XVF3000 — 4-mic array, USB, far-field audio input
- Logitech webcam — vision input
- UE Boom — optional alert tone only, not voice output
- Mac Mini Apple Silicon (192.168.1.46) — always on, central brain, all heavy inference
- SanDisk 64GB USB drive — Raspberry Pi OS 64-bit

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
- Phase two extends identity to additional known people (girlfriend, etc.)
- Unknown person detected — sends alert to iPhone with short clip if feasible, still image as fallback

### Audio
- Always listening at low power for wake word
- Wake word activates full attention and conversation mode
- Builder speaks — audio transcribed locally on Pi — text sent to Mac Mini
- LLM processes on Mac Mini — response returns as text
- Response displays in app and optionally in terminal — no voice output
- Sound anomaly detection is a future capability — not phase one

### Conversation and Memory
- Persistent conversation memory across sessions via Supabase
- Leofric knows its name, responds in conversation as Leofric
- Conversation history viewable in app

### Alerting
- Motion detected while builder is away — app notification
- Unknown person in frame — app notification with image or clip
- All events logged with timestamp and node identifier

---

## The App — iOS First

- Built for iPhone, Apple ecosystem only for now
- Android is a future consideration if this becomes a product
- Core screens:
  - Live camera feed, selectable by node
  - Alert feed with timestamps and thumbnails
  - Conversation interface — type or speak to Leofric, response appears as text
  - Node status — which nodes are active, last seen timestamp
- Push notifications for motion and unknown person events
- Builder has shipped two prior iOS apps — App Store Connect familiarity assumed

---

## The Central Brain — Mac Mini

- Always on at 192.168.1.46
- Flask API server receiving data from Pi nodes
- Ollama running local LLM (Llama 3.2 or better)
- Supabase for persistent memory, event logs, identity data
- Serves live feed and alert data to the iOS app
- Never needs to be touched once configured — set and forget

---

## The Build Phases

### Phase One — Core Loop
One node. Motion detection working. Person detection working. Identity recognition learning the builder. Basic conversation via wake word with text response in terminal. All events logging to Mac Mini. This is the foundation everything else sits on.

### Phase Two — App
iOS app consuming live feed, alert notifications, conversation interface, node status. Leofric moves from a terminal project to a product.

### Phase Three — Vision Intelligence Depth
Identity expanded to additional known people. Unknown person alert with clip. Anomaly detection begins. The system starts making intelligent distinctions rather than flagging everything.

### Phase Four — Second Node
Room to room presence handoff. Conversation context follows the builder between rooms. Distributed coordination between nodes. This is the architecture story for interviews.

### Phase Five — Form Factor
Compact hardware replacing the development rig. Clean mount. Single cable. Looks like something that belongs on a wall.

---

## What This Is Not

- Not a cloud-dependent system — everything runs locally, privacy is a feature
- Not a voice assistant in the Alexa or Siri sense — Leofric does not speak out loud
- Not a toy or demo — it runs in the home and is used daily
- Not finished at any single phase — it grows continuously

---

## Notes for Claude Code

- The Mac Mini Flask server and Ollama setup from the prior Mercia project are still valid and do not need to be rebuilt
- Mac Mini IP: 192.168.1.46, Flask on port 5000
- All new code is written from scratch — do not reference or copy Mercia codebase
- Pi will need setup guidance when deployment begins — treat it as a fresh start
- Prioritize clean, well-structured Python that the builder can read, explain, and defend in an interview
- Every architectural decision should be explainable in plain English — no magic, no black boxes
- When in doubt, build the simpler thing first and make it work completely before adding complexity
