"""
scripts/test_person.py — Phase 1E person detection test (confirmation mode).

Runs the layered pipeline as it will run for real: motion every frame, HOG only
on motion frames (throttled), using the calibrated confidence threshold from
config. Because HOG fires intermittently, "person present" is a short-lived state
that a single confident hit sets and that clears after a couple of still seconds.
Logs PERSON DETECTED on the rising edge and saves an annotated frame (green =
motion, blue = person).

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

WATCH_SECONDS = 30
PERSON_CHECK_INTERVAL = 0.5  # seconds between HOG runs (it is expensive)
PERSON_GONE_AFTER = 2.0  # seconds without a hit before we declare the person gone


def main():
    setup_logging()
    motion = MotionDetector()
    person = PersonDetector()  # uses config.PERSON_MIN_CONFIDENCE (0.5)

    with Camera() as cam:
        logger.info("Warming up background model (2s) — hold still...")
        warmup_end = time.time() + 2
        while time.time() < warmup_end:
            f = cam.read()
            if f is not None:
                motion.process(f)
            time.sleep(0.03)

        logger.info(
            "Watching %ds — stand ~8ft back, full body in frame, walk around.",
            WATCH_SECONDS,
        )
        person_present = False
        last_check = 0.0
        last_person_at = 0.0
        saved = False
        end = time.time() + WATCH_SECONDS

        while time.time() < end:
            frame = cam.read()
            if frame is None:
                continue

            m = motion.process(frame)

            if m.detected and (time.time() - last_check) >= PERSON_CHECK_INTERVAL:
                last_check = time.time()
                p = person.process(frame)
                if p.detected:
                    last_person_at = time.time()
                    if not person_present:
                        person_present = True
                        logger.info(
                            "PERSON DETECTED — %d person(s), score(s)=%s",
                            len(p.boxes),
                            p.weights,
                        )
                        if not saved:
                            annotated = frame.copy()
                            for (x, y, w, h) in m.boxes:
                                cv2.rectangle(
                                    annotated, (x, y), (x + w, y + h), (0, 255, 0), 2
                                )
                            for (x, y, w, h) in p.boxes:
                                cv2.rectangle(
                                    annotated, (x, y), (x + w, y + h), (255, 0, 0), 3
                                )
                            cv2.imwrite(
                                str(config.DATA_DIR / "person_test.jpg"), annotated
                            )
                            logger.info("Saved annotated frame")
                            saved = True

            if person_present and (time.time() - last_person_at) > PERSON_GONE_AFTER:
                person_present = False
                logger.info("person gone")

            time.sleep(0.01)

        logger.info("Done. If PERSON DETECTED appeared above, 1E is working.")


if __name__ == "__main__":
    main()
