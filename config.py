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

# --- Mac Mini brain ---
MAC_MINI_URL = os.getenv("MAC_MINI_URL", "http://192.168.1.46:5000")

# --- Filesystem paths ---
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"


# --- Secrets ---
# Exposed as functions, not module constants, so that simply importing config
# never crashes before the keys exist. A subsystem calls these only when it
# actually needs to connect (Phases 1G and 1H wire them in).
def picovoice_access_key() -> str:
    return _require("PICOVOICE_ACCESS_KEY")


def supabase_url() -> str:
    return _require("SUPABASE_URL")


def supabase_key() -> str:
    return _require("SUPABASE_KEY")
