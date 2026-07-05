# Leofric — Architecture Decisions

A running log of notable technical decisions and deviations from the original
spec, with the reasoning — so the "why" behind each choice isn't lost later.

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
