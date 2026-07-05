"""
scripts/test_person.py — Phase 1E person detection test (diagnostic mode).

This version is verbose on purpose so we can tell framing problems apart from
detector problems:
  - logs when motion fires (so we know the camera actually sees you moving),
  - runs the HOG detector with NO confidence filter, logging every raw hit and
    its SVM score (so we can calibrate the real threshold from actual numbers),
  - always saves an annotated frame (green = motion regions, blue = person hits)
    of the last motion frame, so we can see exactly what the detector was looking at,
  - prints a summary at the end.

Run from the project root with the venv active:
    python scripts/test_person.py
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
from vision.person import PersonDetector  # noqa: E402

logger = logging.getLogger("test_person")

WATCH_SECONDS = 45
PERSON_CHECK_INTERVAL = 0.7  # seconds between HOG runs (it is expensive)


def main():
    setup_logging()
    motion = MotionDetector()
    # min_confidence=0.0 for this diagnostic: show every raw HOG hit and its score.
    person = PersonDetector(min_confidence=0.0)

    with Camera() as cam:
        logger.info("Warming up background model (2s) — hold still...")
        warmup_end = time.time() + 2
        while time.time() < warmup_end:
            f = cam.read()
            if f is not None:
                motion.process(f)
            time.sleep(0.03)

        logger.info(
            "Watching %ds — stand ~8ft back, FULL BODY in frame, keep moving.",
            WATCH_SECONDS,
        )
        motion_active = False
        motion_frames = 0
        hog_checks = 0
        best_score = 0.0
        last_check = 0.0
        end = time.time() + WATCH_SECONDS

        while time.time() < end:
            frame = cam.read()
            if frame is None:
                continue

            m = motion.process(frame)

            if m.detected:
                motion_frames += 1
                if not motion_active:
                    motion_active = True
                    logger.info("motion detected (area=%d px)", m.total_area)
            else:
                motion_active = False

            if m.detected and (time.time() - last_check) >= PERSON_CHECK_INTERVAL:
                last_check = time.time()
                hog_checks += 1
                p = person.process(frame)
                if p.weights:
                    best_score = max(best_score, max(p.weights))
                logger.info(
                    "  HOG check #%d: %d raw hit(s), scores=%s",
                    hog_checks,
                    len(p.boxes),
                    p.weights,
                )
                # Save an annotated view of what the detector was looking at.
                annotated = frame.copy()
                for (x, y, w, h) in m.boxes:
                    cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
                for (x, y, w, h) in p.boxes:
                    cv2.rectangle(annotated, (x, y), (x + w, y + h), (255, 0, 0), 3)
                cv2.imwrite(str(config.DATA_DIR / "person_test.jpg"), annotated)

            time.sleep(0.01)

        logger.info(
            "SUMMARY: %d motion frames, %d HOG checks, best person score=%.2f",
            motion_frames,
            hog_checks,
            best_score,
        )
        if hog_checks == 0:
            logger.info("No HOG checks ran -> no motion was seen. Framing/movement issue.")
        elif best_score == 0.0:
            logger.info("HOG ran but found no people -> detector/framing issue, not motion.")


if __name__ == "__main__":
    main()
