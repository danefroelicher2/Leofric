# CLAUDE.md — Leofric project state & handoff

Read this first. It's the working memory for any Claude instance on this project.
Last updated: 2026-07-05 (end of a long build session).

---

## What Leofric is
A local-first home-intelligence system. A Raspberry Pi node senses (camera + mic);
a Mac Mini runs the LLM "brain"; everything is local (privacy is a feature). Long
game: a portfolio-grade distributed system for defense/robotics/intel roles. See
`docs/PROJECT_SPEC.md`, `docs/BUILDER_PROFILE.md`, `docs/ROADMAP.md`.

## The three machines
- **Windows PC** (this dev machine): the git repo lives here at
  `C:\Users\danef\Downloads\Programming\Current\Leofric`. Remote:
  `github.com/danefroelicher2/Leofric` (**private**).
- **Raspberry Pi 5** (`leofric.local`, user `dane`, ~`192.168.1.20`): the sensing
  node. Runs this repo at `/home/dane/leofric`, venv at `venv/`, Debian trixie,
  **Python 3.13**, aarch64. Camera = Logitech BRIO `/dev/video0`; mic = ReSpeaker
  4-mic array (ALSA card 2, opens as 16 kHz mono).
- **Mac Mini brain** (`Danes-Mac-mini-3.local`): Ollama (`llama3.2`) behind a
  Flask server on `:5000` at `~/leofric-brain/server.py`, auto-starts via a
  LaunchAgent. **Use the `.local` hostname, not the IP** — DHCP drifts (it was
  `.46`, now `.19`, no reservation possible on the router). See `docs/MAC_STATUS.md`.

## Workflow (important)
Develop on Windows → commit → push → **`git pull` on the Pi** → run/test on real
hardware. I (Claude) can edit Windows files directly but **cannot** touch the Pi
or Mac directly — I hand the user commands. The user runs two terminal tabs:
- **Pi tab**: prompt `(venv) dane@leofric:~/leofric $` — runs Leofric/bash. `&&` OK.
- **Windows tab**: prompt `PS C:\Users\danef>` — for `scp` file transfers. **PowerShell
  5.1: `&&` is NOT valid.** A very common mistake is running a command in the wrong
  tab — call out which tab every time.
To view Pi files (images/audio), `scp` them to Windows and open. Activate the venv
in a fresh SSH session: `cd ~/leofric && source venv/bin/activate`.

## Status — Phase 1 (Core Loop) — ✅ COMPLETE (2026-07-06)
**1A–1K ALL COMPLETE and verified on hardware. Next phase is 2 (iOS app).**
- 1A hardware, 1B skeleton+venv+deploy key, 1C camera (threaded, 720p),
  1D motion (MOG2), 1E person (**MobileNet-SSD DNN**), 1F identity (**YuNet+SFace**,
  builder "dane" enrolled at 0.80), 1G Supabase (events+conversations, RLS),
  1H wake word (**openWakeWord**, currently pretrained **"hey jarvis"**),
  1I transcription (**faster-whisper base**), 1J brain (**Ollama llama3.2** on the
  Mac — we built it; the spec wrongly assumed it existed).
- **1K**: `main.py` (VisionWorker + AudioWorker threads, graceful shutdown) +
  `deploy/leofric.service` (systemd) installed and **verified on hardware**. Service
  is `enabled` + `active (running)`; **reboot test PASSED** (Pi power-cycled, Leofric
  auto-started in ~30s with nobody logged in). Full voice loop works **headless**
  (wake word → transcribe → Mac brain → coherent reply → Supabase). Vision (motion +
  person + identity `dane`) logging cleanly the whole time.
- **Transcription hardening (2026-07-06):** enabled faster-whisper `vad_filter=True`
  (Silero VAD) — kills the "invent words from marginal/far-field audio" hallucination
  (e.g. it used to emit "The problem is it." from noise). Weak audio now returns
  empty instead of a false transcript. Zero added latency. Root cause of the earlier
  garble was diagnosed as background audio (a video playing) + Whisper `base`
  hallucinating on non-speech — NOT CPU contention (disproved: clean transcription
  under full vision load). `scripts/measure_audio.py` added as a live mic-RMS meter
  for VAD tuning (room ambient ~115 RMS, speech 1500–5000+, threshold 500 confirmed).

### NEXT TASK — Phase 2A (iOS app begins)
Phase 1 is done. Start Phase 2 (see docs/ROADMAP.md Phase 2). First up: expand the
Mac Mini Flask API (`GET /events`, `GET /feed` MJPEG, `GET /conversations`,
`GET /nodes`, existing `POST /chat`) so the iOS app has data to consume, then
scaffold the Xcode project on the Mac.

**Small durability follow-up before/while doing Phase 2:** Mac Mini reboot test —
the brain LaunchAgent was only kill-tested, never reboot-tested. Reboot the Mac,
then from the Pi `curl http://Danes-Mac-mini-3.local:5000/` to confirm the brain
auto-starts. This closes the last "a week later" gap on the Mac side.

### Deferred / TODO
- **Custom "Hey Leofric" wake word**: train via openWakeWord's free Colab, drop
  `hey_leofric.onnx` into `data/models/` — code auto-detects it (one-file swap).
  Until then the wake phrase is "Hey Jarvis".
- Mac Mini reboot test for the brain LaunchAgent (only kill-tested so far).
- Mac static IP (using hostname works around it for now).

## Key decisions (full reasoning in docs/DECISIONS.md)
We swapped several spec'd tools because they didn't fit the Pi / Python 3.13:
- **Person**: HOG → MobileNet-SSD DNN (ADR-001) — HOG only does standing full bodies.
- **Identity**: dlib/face_recognition → OpenCV YuNet+SFace (ADR-002) — no dlib build.
- **Wake word**: Porcupine/Picovoice → openWakeWord (ADR-003) — no Picovoice account.
- **Transcription**: openai-whisper → faster-whisper (ADR-004) — avoid torch.
- **Brain**: built the Mac Mini server from scratch (ADR-005) — it never existed.

## Environment gotchas (Python 3.13 on the Pi bit us repeatedly)
- **Check wheel availability before choosing a library** (`pip index` / PyPI JSON).
  Many packages lack cp313 aarch64 wheels. This drove several of the swaps above.
- OpenCV pinned `<5` (OpenCV 5 removed HOGDescriptor; we use DNN now but keep the pin).
- openWakeWord 0.6.0: `Model(wakeword_model_paths=[<path>])`, models are bundled
  `.onnx`, **no** `inference_framework` kwarg, no `download_models`.
- pyaudio needs `python3-dev` + `portaudio19-dev` (apt) to build on the Pi.
- Supabase: DB managed **directly via the claude.ai Supabase MCP connector** (Dane's
  preference — don't hand him dashboard SQL). service_role key in the Pi's `.env`.

## Repo layout
`main.py` (integrated loop) · `config.py` (settings, loads `.env`) · `log.py` ·
`vision/` (camera, motion, person, identity) · `audio/` (microphone, wakeword,
transcription) · `brain/` (client, conversation) · `storage/` (events → Supabase) ·
`macmini/` (the Mac's Flask server) · `scripts/` (per-phase test_*.py, fetch_models.py) ·
`deploy/leofric.service` · `data/` (models, known_faces.npz — gitignored) ·
`docs/` (SPEC, ROADMAP, DECISIONS, MACDOCS, MAC_STATUS).
Secrets live only in the Pi's `.env` (gitignored). Models fetched by
`scripts/fetch_models.py`.
