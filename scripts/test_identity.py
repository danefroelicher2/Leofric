"""
scripts/test_identity.py — Phase 1F identity test.

Runs face recognition live for a window and logs, per detected face, whether it
is the builder or unknown along with the cosine similarity. Saves an annotated
frame (green box for the builder, red for unknown, each labelled name + score).

Enrol first:  python scripts/enroll_face.py

Usage (venv active, from project root):
    python scripts/test_identity.py
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
from vision.identity import IdentityRecognizer  # noqa: E402

logger = logging.getLogger("test_identity")

WATCH_SECONDS = 20
CHECK_INTERVAL = 0.4


def main():
    setup_logging()
    rec = IdentityRecognizer()
    if rec.enrolled_count == 0:
        logger.error("No enrolled faces. Run: python scripts/enroll_face.py")
        return

    logger.info(
        "Watching %ds — %d enrolled sample(s). Sit in view; then try covering "
        "your face or having someone else appear to see 'unknown'.",
        WATCH_SECONDS,
        rec.enrolled_count,
    )
    last_check = 0.0
    saved = False
    end = time.time() + WATCH_SECONDS

    with Camera() as cam:
        while time.time() < end:
            frame = cam.read()
            if frame is None:
                continue
            if (time.time() - last_check) < CHECK_INTERVAL:
                time.sleep(0.01)
                continue
            last_check = time.time()

            faces = rec.classify(frame)
            if not faces:
                continue

            for f in faces:
                logger.info("face: %s (similarity=%.3f)", f.name, f.similarity)

            if not saved:
                annotated = frame.copy()
                for f in faces:
                    x, y, w, h = f.box
                    is_builder = f.name != "unknown"
                    color = (0, 255, 0) if is_builder else (0, 0, 255)
                    cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
                    cv2.putText(
                        annotated,
                        f"{f.name} {f.similarity:.2f}",
                        (x, max(0, y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        color,
                        2,
                    )
                cv2.imwrite(str(config.DATA_DIR / "identity_test.jpg"), annotated)
                logger.info("Saved annotated frame")
                saved = True

    logger.info("Done.")


if __name__ == "__main__":
    main()
