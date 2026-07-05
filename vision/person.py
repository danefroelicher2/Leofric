"""
vision/person.py — person detection via HOG + linear SVM (OpenCV built-in).

HOG (Histogram of Oriented Gradients) paired with a pretrained pedestrian SVM is
a classic, dependency-free person detector. It is far more expensive than motion
detection, so in the pipeline it runs only on frames where motion already fired:
the cheap trigger gates the costly classifier. We also downscale the frame first
— HOG cost grows with pixel count, and a person is still clearly detectable at
640px wide — then scale the resulting boxes back to full-frame coordinates.
"""

from dataclasses import dataclass, field

import cv2

import config


@dataclass
class PersonResult:
    detected: bool
    boxes: list = field(default_factory=list)  # (x, y, w, h) in ORIGINAL frame coords


class PersonDetector:
    def __init__(self, detect_width=None, min_confidence=None):
        self.detect_width = detect_width or config.PERSON_DETECT_WIDTH
        self.min_confidence = (
            min_confidence if min_confidence is not None else config.PERSON_MIN_CONFIDENCE
        )
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def process(self, frame) -> PersonResult:
        h0, w0 = frame.shape[:2]
        scale = self.detect_width / float(w0)
        small = cv2.resize(frame, (self.detect_width, int(h0 * scale)))

        rects, weights = self._hog.detectMultiScale(
            small,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
        )

        inv = 1.0 / scale
        boxes = []
        for (x, y, w, h), weight in zip(rects, weights):
            # weight is the SVM decision score; drop weak (likely false) hits.
            if float(weight) < self.min_confidence:
                continue
            boxes.append((int(x * inv), int(y * inv), int(w * inv), int(h * inv)))

        return PersonResult(detected=bool(boxes), boxes=boxes)
