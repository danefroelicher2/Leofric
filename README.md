# Leofric

A local-first home intelligence system. Physical nodes mounted in rooms watch and
listen continuously; a central brain on a Mac Mini coordinates them; an iPhone app
(later phases) gives a live window into what Leofric sees and has flagged.

Leofric does not speak out loud. It watches, listens, thinks, and communicates
through the app. Everything runs on local hardware — privacy is a design feature.

## Architecture (Phase 1)

- **Edge node** — Raspberry Pi 5 (8GB) running this code, with a camera and mic
  array. Does motion, person, and identity detection locally, plus wake-word
  listening and on-device speech-to-text.
- **Brain** — Mac Mini on the LAN running Ollama (Llama 3.2) behind a Flask API.
  The Pi sends transcribed speech; the Mac returns a text response.
- **Storage** — Supabase for the persistent event log and conversation history.

## Layout

| Path | Responsibility |
|---|---|
| `main.py` | Entry point — starts all subsystems (built in Phase 1K) |
| `config.py` | Loads settings/secrets from `.env`, exposes them as constants |
| `vision/` | camera, motion, person, identity |
| `audio/` | microphone, wake word, transcription |
| `brain/` | HTTP client to the Mac Mini + conversation memory |
| `storage/` | Supabase event logging |
| `scripts/` | operational scripts (e.g. hardware check) |
| `data/` | runtime artifacts (face encodings, keyword file) — gitignored |
| `logs/` | runtime logs — gitignored |
| `docs/` | project spec, roadmap, setup notes |

## Development workflow

Code is written on a Windows dev machine and synced to the Pi via GitHub:
edit → commit → push → `git pull` on the Pi → run and test on real hardware.
The Pi is the deployment target; hardware-dependent testing happens there.

## Setup (on the Pi)

```bash
git clone https://github.com/danefroelicher2/Leofric.git leofric
cd leofric
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then fill in secrets as phases require them
python main.py
```

## Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md). Current phase: **Phase 1 — Core Loop**.
