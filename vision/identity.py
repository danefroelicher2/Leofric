"""
vision/identity.py — face detection + recognition (OpenCV YuNet + SFace).

Two small DNNs work together:
  - YuNet detects faces and their landmarks (eyes, nose, mouth corners).
  - SFace turns an aligned face crop into a 128-dimensional embedding — a point
    in "face space" where the same person's faces cluster close together.

To recognise someone we compare a live face's embedding against the enrolled
embeddings using cosine similarity; above a threshold it's a match. This is the
same principle as dlib's face_recognition, but built on models we already have
through OpenCV — no heavy dlib build. Phase 1 only needs "builder vs unknown",
but embeddings are stored with names so more people can be added later.
"""

from dataclasses import dataclass

import cv2
import numpy as np

import config

# SFace compares two embeddings; this constant selects cosine similarity.
_COSINE = cv2.FaceRecognizerSF_FR_COSINE


@dataclass
class FaceResult:
    box: tuple  # (x, y, w, h)
    name: str  # builder name, or "unknown"
    similarity: float  # cosine similarity to the best-matching enrolled face


class IdentityRecognizer:
    def __init__(self):
        for path in (config.FACE_DETECT_MODEL, config.FACE_RECOG_MODEL):
            if not path.exists():
                raise RuntimeError(
                    f"Face model {path.name} not found. "
                    f"Run:  python scripts/fetch_models.py"
                )
        # Input size is reset per-frame in detect_faces(); this is a placeholder.
        self._detector = cv2.FaceDetectorYN_create(
            str(config.FACE_DETECT_MODEL),
            "",
            (320, 320),
            config.FACE_DETECT_SCORE,  # score threshold
            0.3,  # NMS threshold
            5000,  # top_k
        )
        self._recognizer = cv2.FaceRecognizerSF_create(
            str(config.FACE_RECOG_MODEL), ""
        )
        self._known_embeddings, self._known_labels = self._load_known()

    def _load_known(self):
        if not config.KNOWN_FACES_FILE.exists():
            return np.zeros((0, 128), dtype=np.float32), []
        data = np.load(config.KNOWN_FACES_FILE, allow_pickle=True)
        return data["embeddings"].astype(np.float32), list(data["labels"])

    @property
    def enrolled_count(self):
        return len(self._known_labels)

    def detect_faces(self, frame):
        """Return YuNet face rows (each: 4 bbox + 10 landmark + 1 score = 15)."""
        h, w = frame.shape[:2]
        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(frame)
        return faces if faces is not None else np.empty((0, 15), dtype=np.float32)

    def embed(self, frame, face_row):
        """Align a detected face and return its 128-d SFace embedding (1, 128)."""
        aligned = self._recognizer.alignCrop(frame, face_row)
        return self._recognizer.feature(aligned)

    def classify(self, frame):
        """Return a FaceResult for every detected face in the frame."""
        results = []
        for row in self.detect_faces(frame):
            x, y, bw, bh = row[:4].astype(int)
            feature = self.embed(frame, row)
            name, sim = self._match(feature)
            results.append(
                FaceResult(box=(int(x), int(y), int(bw), int(bh)), name=name, similarity=sim)
            )
        return results

    def _match(self, feature):
        """Compare one embedding to all enrolled ones; return (name, similarity)."""
        if not self._known_labels:
            return "unknown", 0.0
        best_name, best_sim = "unknown", -1.0
        for emb, label in zip(self._known_embeddings, self._known_labels):
            sim = self._recognizer.match(feature, emb.reshape(1, -1), _COSINE)
            if sim > best_sim:
                best_sim, best_name = sim, label
        if best_sim >= config.FACE_MATCH_THRESHOLD:
            return best_name, float(best_sim)
        return "unknown", float(best_sim)
