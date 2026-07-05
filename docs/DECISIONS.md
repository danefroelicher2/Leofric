# Leofric — Architecture Decisions

A running log of notable technical decisions and deviations from the original
spec, with the reasoning — so the "why" behind each choice isn't lost later.

## ADR-005: Mac Mini brain built from scratch (spec assumed it existed)
**Date:** 2026-07-05

The spec described the Mac Mini as already running a Flask API + Ollama on
`192.168.1.46:5000`, "do not rebuild." In reality the Mac was powered off, and once
on, a full LAN scan found no Flask (:5000) and no Ollama (:11434) — the brain was
never set up (global notes also list the central brain as deferred). So we build it:
a small Flask server (`macmini/server.py`) fronting Ollama/Llama 3.2, defining a
clean contract (`POST /chat {message, history} -> {response}`). The Mac's DHCP IP
had also drifted off `.46`; we will reserve a static IP. Owning both sides is a
better outcome than inheriting a black-box server.

## ADR-004: Transcription — faster-whisper instead of openai-whisper
**Date:** 2026-07-05

The roadmap says "Whisper (local, runs on the Pi)". The reference implementation,
openai-whisper, depends on the full PyTorch stack — hundreds of MB and slow on the
Pi's CPU. **faster-whisper** runs the same Whisper models on the CTranslate2
backend: ~4x faster on CPU, much lower memory, with int8 quantization. It installs
cleanly on the Pi (pure-Python wrapper + a `ctranslate2` cp313 aarch64 wheel).
Same models and accuracy, far better fit for the hardware. Starting at the `base`
model size per the roadmap; will bump to `small` if accuracy is poor.

## ADR-003: Wake word — openWakeWord instead of Porcupine / Picovoice
**Date:** 2026-07-05

The spec explicitly chose Porcupine (Picovoice) and said *not* to use openWakeWord.
Porcupine requires a Picovoice account + AccessKey. The builder could not create or
recover an account (the old account was deleted; new signup rejected a personal
email), which hard-blocked Porcupine with no workaround.

**Decision:** switch to **openWakeWord**. It is free, fully offline, needs no
account, is the recognized open-source wake-word engine, and installs on the Pi
(pure-Python package + an `onnxruntime` cp313 aarch64 wheel that exists on PyPI).
Vosk (constrained-grammar ASR) was considered but is heavier for a 24/7 always-on
listener; openWakeWord is purpose-built for the wake-word role and keeps everything
on-device (privacy preserved, as with the original Porcupine plan).

**Rollout:** bring the audio + wake-word pipeline up first with a *pretrained*
model (`hey_jarvis`) to validate it end-to-end with zero friction, then train a
custom **"Hey Leofric"** model (free, via openWakeWord's training notebook) and
swap it in. Only the engine changes — `audio/wakeword.py` and the rest of the
architecture stay the same.

## ADR-002: Face identity — OpenCV YuNet + SFace instead of dlib / face_recognition
**Date:** 2026-07-05

The roadmap specified the dlib-based `face_recognition` library. dlib is a heavy
C++ compile that is slow and fragile on the Pi and risky on Python 3.13. OpenCV
ships **YuNet** (face detection) + **SFace** (128-d embeddings) built in — same
principle, no new dependency, fast on the Pi. Builder recognised at 0.80 cosine
similarity vs a 0.363 threshold (>2x margin).

## ADR-001: Person detection — MobileNet-SSD DNN instead of HOG
**Date:** 2026-07-05

The roadmap specified OpenCV's HOG pedestrian detector. HOG only reliably detects
full-body, upright, standing people at a distance. Leofric's deployment target is
a corner-mounted node watching a room: seated people, half-bodies, and multiple
people at varied distances. Switched to a **MobileNet-SSD** single-shot detector
via OpenCV's DNN module (no new dependency). Detected the builder seated at 0.97
confidence.
