"""
scripts/test_person.py — Phase 1E person detection test.

Demonstrates the layered pipeline: motion detection runs every frame, and the
costly HOG person detector runs ONLY on frames where motion fired (and at most
a few times a second). Person events are logged separately from raw motion so
you can see the distinction. Saves an annotated frame (blue boxes) the first
time a person is found.

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
PERSON_CHECK_INTERVAL = 0.5  # don't run the costly HOG detector more often than this
PERSON_GONE_AFTER = 2.0  # seconds without a hit before we declare the person gone


def main():
    setup_logging()
    motion = MotionDetector()
    person = PersonDetector()

    with Camera() as cam:
        logger.info("Warming up background model (2s) — hold still...")
        warmup_end = time.time() + 2
        while time.time() < warmup_end:
            f = cam.read()
            if f is not None:
                motion.process(f)
            time.sleep(0.03)

        logger.info(
            "Watching for %ds — walk into frame so it can find a person.",
            WATCH_SECONDS,
        )
        person_present = False
        last_person_check = 0.0
        last_person_at = 0.0
        saved = False
        end = time.time() + WATCH_SECONDS

        while time.time() < end:
            frame = cam.read()
            if frame is None:
                continue

            m = motion.process(frame)

            # Costly detector runs only on motion frames, throttled in time.
            if m.detected and (time.time() - last_person_check) >= PERSON_CHECK_INTERVAL:
                last_person_check = time.time()
                p = person.process(frame)
                if p.detected:
                    last_person_at = time.time()
                    if not person_present:
                        person_present = True
                        logger.info("PERSON DETECTED — %d person(s)", len(p.boxes))
                        if not saved:
                            annotated = frame.copy()
                            for (x, y, w, h) in p.boxes:
                                cv2.rectangle(
                                    annotated, (x, y), (x + w, y + h), (255, 0, 0), 2
                                )
                            out = config.DATA_DIR / "person_test.jpg"
                            cv2.imwrite(str(out), annotated)
                            logger.info("Saved annotated frame to %s", out)
                            saved = True

            if person_present and (time.time() - last_person_at) > PERSON_GONE_AFTER:
                person_present = False
                logger.info("person gone")

            time.sleep(0.01)

        logger.info("Done. Full log at %s", config.LOGS_DIR / "leofric.log")


if __name__ == "__main__":
    main()
