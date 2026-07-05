"""
scripts/enroll_face.py — enrol the builder's face.

Captures many frames from the live camera, detects the largest face in each,
computes its SFace embedding, and saves the collection to data/known_faces.npz
under the builder's name. Re-running replaces any previous enrolment for that
same name (other people's enrolments are kept).

While it runs, look at the camera and SLOWLY turn your head and change expression
so the enrolled set covers a range of angles and lighting.

Usage (venv active, from project root):
    python scripts/enroll_face.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

import config  # noqa: E402
from vision.camera import Camera  # noqa: E402
from vision.identity import IdentityRecognizer  # noqa: E402

TARGET_SAMPLES = 25


def largest_face(faces):
    """Pick the biggest face row (col 2*3 = w*h) or None if there are none."""
    if faces is None or len(faces) == 0:
        return None
    areas = faces[:, 2] * faces[:, 3]
    return faces[int(np.argmax(areas))]


def main():
    rec = IdentityRecognizer()
    collected = []

    print(f"Enrolling '{config.BUILDER_NAME}'.")
    print("Look at the camera; slowly turn your head and vary expression.")
    print(f"Collecting {TARGET_SAMPLES} samples...")

    with Camera() as cam:
        while len(collected) < TARGET_SAMPLES:
            frame = cam.read()
            if frame is None:
                continue
            face = largest_face(rec.detect_faces(frame))
            if face is None or float(face[-1]) < config.FACE_DETECT_SCORE:
                continue  # no confident face this frame
            collected.append(rec.embed(frame, face).flatten())
            print(f"  captured {len(collected)}/{TARGET_SAMPLES}")
            time.sleep(0.25)  # spread samples across poses over time

    new_emb = np.array(collected, dtype=np.float32)
    new_lab = [config.BUILDER_NAME] * len(collected)

    # Merge with existing enrolments, replacing any prior samples for this name.
    emb_all, lab_all = [], []
    if config.KNOWN_FACES_FILE.exists():
        old = np.load(config.KNOWN_FACES_FILE, allow_pickle=True)
        for emb, label in zip(old["embeddings"], list(old["labels"])):
            if label == config.BUILDER_NAME:
                continue
            emb_all.append(emb)
            lab_all.append(label)
    emb_all.extend(list(new_emb))
    lab_all.extend(new_lab)

    config.DATA_DIR.mkdir(exist_ok=True)
    np.savez(
        config.KNOWN_FACES_FILE,
        embeddings=np.array(emb_all, dtype=np.float32),
        labels=np.array(lab_all),
    )
    print(
        f"Saved {len(collected)} samples for '{config.BUILDER_NAME}' "
        f"to {config.KNOWN_FACES_FILE}"
    )


if __name__ == "__main__":
    main()
