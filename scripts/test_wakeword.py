"""
scripts/test_wakeword.py — Phase 1H wake-word bring-up test.

Listens on the ReSpeaker and logs whenever the wake word fires. Uses the custom
Hey-Leofric model if data/models/hey_leofric.onnx exists, otherwise a pretrained
model (config.WAKEWORD_PRETRAINED, default 'hey_jarvis') so we can validate the
mic + engine before the custom model is trained.

First run downloads the openWakeWord models (needs internet). Ctrl+C to stop.

Usage (venv active, from project root):
    python scripts/test_wakeword.py
"""

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openwakeword import utils as oww_utils  # noqa: E402

import config  # noqa: E402
from log import setup_logging  # noqa: E402
from audio.microphone import Microphone  # noqa: E402
from audio.wakeword import WakeWord  # noqa: E402

logger = logging.getLogger("test_wakeword")

COOLDOWN = 1.5  # seconds; collapse a single utterance into one log line


def main():
    setup_logging()
    logger.info("Ensuring openWakeWord models are present (first run downloads them)...")
    oww_utils.download_models()

    ww = WakeWord()
    mic = Microphone(
        rate=WakeWord.SAMPLE_RATE, channels=1, frame_length=WakeWord.FRAME_LENGTH
    )
    logger.info(
        "Listening — wake word: %s (threshold %.2f). Say it out loud. Ctrl+C to stop.",
        ww.label,
        ww.threshold,
    )

    count = 0
    last_fire = 0.0
    with mic:
        try:
            while True:
                detected, score = ww.process(mic.read_frame())
                if detected and (time.time() - last_fire) > COOLDOWN:
                    last_fire = time.time()
                    count += 1
                    logger.info("WAKE WORD DETECTED (#%d, score=%.2f)", count, score)
        except KeyboardInterrupt:
            logger.info("Stopped. Total detections: %d", count)


if __name__ == "__main__":
    main()
