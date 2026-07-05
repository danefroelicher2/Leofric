"""
vision/motion.py — motion detection via background subtraction (OpenCV MOG2).

How it works: MOG2 models each pixel's recent history as a mixture of Gaussians
and flags pixels that no longer fit as "foreground" — i.e. something changed
there. We clean up that mask, find connected regions, and ignore any smaller
than a minimum area so lighting flicker and sensor noise don't register as
motion. This is cheap to run, so it acts as the first-stage trigger: the
expensive detectors (person, identity) only run on frames where motion fired.
"""

from dataclasses import dataclass, field

import cv2

import config


@dataclass
class MotionResult:
    """Per-frame motion outcome."""

    detected: bool
    boxes: list = field(default_factory=list)  # list of (x, y, w, h) regions
    total_area: int = 0


class MotionDetector:
    def __init__(self, min_area=None, history=500, var_threshold=16):
        self.min_area = min_area if min_area is not None else config.MOTION_MIN_AREA
        # detectShadows=True so we can drop shadow pixels (MOG2 marks them 127),
        # which stops a person's moving shadow from inflating the motion area.
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=history, varThreshold=var_threshold, detectShadows=True
        )

    def process(self, frame) -> MotionResult:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)  # smooth out pixel noise
        mask = self._subtractor.apply(gray)

        # Keep only definite foreground (255); discard shadows (127) and background (0).
        _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)
        # Dilate to merge nearby fragments of the same moving object.
        mask = cv2.dilate(mask, None, iterations=2)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        boxes = []
        total_area = 0
        for c in contours:
            area = cv2.contourArea(c)
            if area < self.min_area:
                continue
            total_area += int(area)
            boxes.append(cv2.boundingRect(c))  # (x, y, w, h)

        return MotionResult(detected=bool(boxes), boxes=boxes, total_area=total_area)
