"""
scripts/test_person.py — Phase 1E person detection test (MobileNet-SSD).

Runs the DNN person detector on a steady cadence so it catches a seated, still
person (not only moving ones) and reports how many people it sees. Logs
PERSON DETECTED on the rising edge with per-person confidence, and saves an
annotated frame (blue boxes labelled with confidence).

Note: in the integrated system (Phase 1K) the detector is gated on motion plus
an occasional sweep, to save CPU. Here we run it on a timer so testing is simple.

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
from vision.person import PersonDetector  # noqa: E402

logger = logging.getLogger("test_person")

WATCH_SECONDS = 20
CHECK_INTERVAL = 0.4  # seconds between detector runs
GONE_AFTER = 2.0  # seconds without a hit before we declare the person gone


def main():
    setup_logging()
    person = PersonDetector()

    with Camera() as cam:
        logger.info(
            "Watching %ds — sit in view; it should detect you. "
            "Bring in another person to see multi-person detection.",
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
            if (time.time() - last_check) < CHECK_INTERVAL:
                time.sleep(0.01)
                continue
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
                        for (x, y, w, h), score in zip(p.boxes, p.weights):
                            cv2.rectangle(
                                annotated, (x, y), (x + w, y + h), (255, 0, 0), 2
                            )
                            cv2.putText(
                                annotated,
                                f"person {score:.2f}",
                                (x, max(0, y - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.6,
                                (255, 0, 0),
                                2,
                            )
                        cv2.imwrite(str(config.DATA_DIR / "person_test.jpg"), annotated)
                        logger.info("Saved annotated frame")
                        saved = True
            elif person_present and (time.time() - last_person_at) > GONE_AFTER:
                person_present = False
                logger.info("person gone")

        logger.info("Done. If PERSON DETECTED appeared above, 1E is working.")


if __name__ == "__main__":
    main()
