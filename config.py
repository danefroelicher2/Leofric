"""
Central configuration for Leofric.

All tunable settings and secrets live in one place. Secrets are loaded from a
.env file (never committed) so they stay out of the GitHub repo. Non-secret
hardware defaults are hard-coded here but can be overridden via .env.

Import anywhere with:  import config   ->   config.CAMERA_DEVICE
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Resolve the project root from this file's location, then load .env (if present)
# into the process environment. Doing it here means every module that imports
# config gets the settings loaded exactly once.
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def _require(name: str) -> str:
    """Return an environment variable, or fail loudly if it is missing.

    Used for secrets that have no safe default. We would rather crash clearly at
    startup than fail mysteriously later when a subsystem tries to connect.
    """
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(
            f"Missing required setting {name!r}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


# --- Filesystem paths (defined early so later settings can build on them) ---
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

# --- Node identity ---
NODE_ID = os.getenv("NODE_ID", "leofric")

# --- Hardware (confirmed in Phase 1A) ---
CAMERA_DEVICE = os.getenv("CAMERA_DEVICE", "/dev/video0")
MIC_CARD = int(os.getenv("MIC_CARD", "2"))

# --- Camera capture settings ---
# 720p at 30fps is a good balance of detail and CPU on the Pi 5. Downstream
# detectors will downscale further; the raw feed stays at this resolution.
CAMERA_WIDTH = int(os.getenv("CAMERA_WIDTH", "1280"))
CAMERA_HEIGHT = int(os.getenv("CAMERA_HEIGHT", "720"))
CAMERA_FPS = int(os.getenv("CAMERA_FPS", "30"))

# --- Motion detection ---
# Minimum contour area (in pixels) to count as motion. Below this we treat a
# region as noise/lighting flicker and ignore it. Tunable; a person at room
# distance is far larger than this.
MOTION_MIN_AREA = int(os.getenv("MOTION_MIN_AREA", "5000"))

# --- Person detection (MobileNet-SSD DNN) ---
# Detection confidence, 0..1. 0.5 is a solid default for SSD: raise it to cut
# false positives, lower it to catch harder cases (partial or distant bodies).
PERSON_MIN_CONFIDENCE = float(os.getenv("PERSON_MIN_CONFIDENCE", "0.5"))

# Pretrained model files. Not committed to git (binary/large) — fetch them once
# with: python scripts/fetch_models.py
MODELS_DIR = DATA_DIR / "models"
PERSON_PROTOTXT = MODELS_DIR / "MobileNetSSD_deploy.prototxt"
PERSON_MODEL = MODELS_DIR / "MobileNetSSD_deploy.caffemodel"

# --- Identity (YuNet face detection + SFace face recognition) ---
FACE_DETECT_MODEL = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
FACE_RECOG_MODEL = MODELS_DIR / "face_recognition_sface_2021dec.onnx"
# YuNet face-detection confidence (0..1) required to accept a face.
FACE_DETECT_SCORE = float(os.getenv("FACE_DETECT_SCORE", "0.8"))
# SFace cosine-similarity threshold: >= this means "same person". 0.363 is the
# model's published operating point. Raise it to be stricter (fewer false matches).
FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", "0.363"))
# Where enrolled face embeddings are stored, and the builder's label.
KNOWN_FACES_FILE = DATA_DIR / "known_faces.npz"
BUILDER_NAME = os.getenv("BUILDER_NAME", "dane")

# --- Audio (ReSpeaker mic + openWakeWord wake word) ---
# The ReSpeaker is found by name so USB re-enumeration doesn't break us.
AUDIO_DEVICE_NAME = os.getenv("AUDIO_DEVICE_NAME", "ReSpeaker")
# Custom "Hey Leofric" model, added after training; if absent we fall back to a
# pretrained model for bring-up. (Engine is openWakeWord — see DECISIONS.md ADR-003.)
WAKEWORD_MODEL = MODELS_DIR / "hey_leofric.onnx"
WAKEWORD_PRETRAINED = os.getenv("WAKEWORD_PRETRAINED", "hey_jarvis")
# Score 0..1 above which the wake word is considered heard.
WAKEWORD_THRESHOLD = float(os.getenv("WAKEWORD_THRESHOLD", "0.5"))

# --- Transcription (faster-whisper, runs locally on the Pi) ---
# Model size: 'tiny' (fastest) -> 'base' -> 'small' (most accurate, slower).
# Start at 'base' per the roadmap; bump to 'small' if accuracy is poor.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
# Energy-based endpointing: record the utterance until the speaker goes quiet.
VAD_SILENCE_RMS = float(os.getenv("VAD_SILENCE_RMS", "500"))  # int16 RMS below = silence
UTTERANCE_SILENCE_SECONDS = float(os.getenv("UTTERANCE_SILENCE_SECONDS", "1.0"))
UTTERANCE_MAX_SECONDS = float(os.getenv("UTTERANCE_MAX_SECONDS", "8"))

# --- Mac Mini brain ---
# mDNS hostname survives DHCP drift (the Mac's IP is not reserved on the router).
# Current IP is 192.168.1.19 if a raw address is ever needed — see docs/MAC_STATUS.md.
MAC_MINI_URL = os.getenv("MAC_MINI_URL", "http://Danes-Mac-mini-3.local:5000")

# --- Frame streaming to the Mac (Phase 2A: live feed for the iOS app) ---
STREAM_ENABLED = os.getenv("STREAM_ENABLED", "1").lower() not in ("0", "false", "no")
STREAM_FPS = float(os.getenv("STREAM_FPS", "4"))
STREAM_JPEG_QUALITY = int(os.getenv("STREAM_JPEG_QUALITY", "70"))  # 0-100

# Node role shapes app behavior: a "security" node is camera-first (person
# notifications on); an "assistant" node is mic-first (no notifications).
NODE_ROLE = os.getenv("NODE_ROLE", "security")

# --- Conversation sessions ---
# A pause longer than this between wake-word exchanges starts a new session
# (= a new chat thread in the app) with fresh short-term context.
SESSION_IDLE_SECONDS = float(os.getenv("SESSION_IDLE_SECONDS", "180"))


# --- Secrets ---
# Exposed as functions, not module constants, so that simply importing config
# never crashes before the keys exist. A subsystem calls these only when it
# actually needs to connect. (openWakeWord needs no key — see DECISIONS.md ADR-003.)
def supabase_url() -> str:
    return _require("SUPABASE_URL")


def supabase_key() -> str:
    return _require("SUPABASE_KEY")
