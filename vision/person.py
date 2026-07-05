"""
vision/person.py — person detection via a MobileNet-SSD deep neural network.

Why a DNN instead of the classic HOG detector: HOG only recognises full-body,
upright, standing pedestrians at a distance. This node is meant to watch a room
from a corner, where it will see seated people, half-bodies, several people at
once, and bodies at many angles and distances. A single-shot detector (SSD) with
a MobileNet backbone handles all of those, runs in real time on the Pi 5 through
OpenCV's DNN module, and needs no extra Python dependencies. In the full pipeline
it still runs on motion frames (plus an occasional sweep), keeping the layered
"cheap trigger gates the costly model" design.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

import config

# MobileNet-SSD was trained on the 20 PASCAL VOC classes (plus background).
# We only care about "person", which is class index 15.
_PERSON_CLASS_ID = 15


@dataclass
class PersonResult:
    detected: bool
    boxes: list = field(default_factory=list)   # (x, y, w, h) in original frame coords
    weights: list = field(default_factory=list)  # confidence 0..1 per box


class PersonDetector:
    def __init__(self, min_confidence=None):
        self.min_confidence = (
            min_confidence if min_confidence is not None else config.PERSON_MIN_CONFIDENCE
        )
        if not config.PERSON_PROTOTXT.exists() or not config.PERSON_MODEL.exists():
            raise RuntimeError(
                f"Person model files not found in {config.MODELS_DIR}. "
                f"Run:  python scripts/fetch_models.py"
            )
        self._net = cv2.dnn.readNetFromCaffe(
            str(config.PERSON_PROTOTXT), str(config.PERSON_MODEL)
        )

    def process(self, frame) -> PersonResult:
        h, w = frame.shape[:2]
        # Standard MobileNet-SSD preprocessing: 300x300 input, scale 1/127.5,
        # mean 127.5 (maps 0..255 pixel values to roughly -1..1).
        blob = cv2.dnn.blobFromImage(
            frame, scalefactor=0.007843, size=(300, 300), mean=127.5
        )
        self._net.setInput(blob)
        detections = self._net.forward()  # shape (1, 1, N, 7)

        boxes, kept = [], []
        for i in range(detections.shape[2]):
            class_id = int(detections[0, 0, i, 1])
            confidence = float(detections[0, 0, i, 2])
            if class_id != _PERSON_CLASS_ID or confidence < self.min_confidence:
                continue
            # Box coords are normalised 0..1; scale back to the full frame.
            x1, y1, x2, y2 = (
                detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            ).astype(int)
            boxes.append((int(x1), int(y1), int(x2 - x1), int(y2 - y1)))
            kept.append(round(confidence, 2))

        return PersonResult(detected=bool(boxes), boxes=boxes, weights=kept)
