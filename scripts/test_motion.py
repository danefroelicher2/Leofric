"""
scripts/test_motion.py — Phase 1D motion detection test.

Watches the camera for a fixed window. Logs a MOTION STARTED event on the rising
edge and a "motion ended" event (with duration) once the scene has been still
for a short cooldown, so the log reads as discrete events instead of one line
per frame. Saves an annotated frame (green boxes around moving regions) the first
time motion is seen, for visual confirmation off the Pi.

Run from the project root with the venv active:
    python scripts/test_motion.py
"""

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402

import config  # noqa: E402
from log import setup_logging  # noqa: E402
from vision.camera import Camera  # noqa: E402
from vision.motion import MotionDetector  # noqa: E402

logger = logging.getLogger("test_motion")

WATCH_SECONDS = 30
COOLDOWN = 1.0  # seconds of stillness before we declare motion "ended"


def main():
    setup_logging()
    detector = MotionDetector()

    with Camera() as cam:
        # Let MOG2 learn the static background before we trust its output — the
        # first frames always look like "motion" while the model initialises.
        logger.info("Warming up background model (2s) — hold still...")
        warmup_end = time.time() + 2
        while time.time() < warmup_end:
            frame = cam.read()
            if frame is not None:
                detector.process(frame)
            time.sleep(0.03)

        logger.info(
            "Watching for motion for %ds — walk in front of the camera.",
            WATCH_SECONDS,
        )
        motion_active = False
        motion_started_at = 0.0
        last_motion_at = 0.0
        saved_annotated = False
        end = time.time() + WATCH_SECONDS

        while time.time() < end:
            frame = cam.read()
            if frame is None:
                continue
            result = detector.process(frame)

            if result.detected:
                last_motion_at = time.time()
                if not motion_active:
                    motion_active = True
                    motion_started_at = last_motion_at
                    logger.info(
                        "MOTION STARTED — %d region(s), area=%d px",
                        len(result.boxes),
                        result.total_area,
                    )
                    if not saved_annotated:
                        annotated = frame.copy()
                        for (x, y, w, h) in result.boxes:
                            cv2.rectangle(
                                annotated, (x, y), (x + w, y + h), (0, 255, 0), 2
                            )
                        out = config.DATA_DIR / "motion_test.jpg"
                        cv2.imwrite(str(out), annotated)
                        logger.info("Saved annotated frame to %s", out)
                        saved_annotated = True
            elif motion_active and (time.time() - last_motion_at) > COOLDOWN:
                motion_active = False
                logger.info(
                    "motion ended — lasted %.1fs", last_motion_at - motion_started_at
                )

            time.sleep(0.03)

        logger.info("Done. Full log at %s", config.LOGS_DIR / "leofric.log")


if __name__ == "__main__":
    main()
