"""
audio/wakeword.py — wake-word detection with openWakeWord.

openWakeWord is an offline, on-device keyword spotter — our replacement for
Porcupine (see docs/DECISIONS.md ADR-003). A small shared feature extractor
(mel-spectrogram + embedding) feeds lightweight per-keyword models. We hand it
16 kHz int16 audio in ~80 ms chunks; predict() returns a score 0..1 per model and
we fire when the best score crosses a threshold.

Uses the custom "Hey Leofric" model (data/models/hey_leofric.onnx) if present,
otherwise a pretrained model for bring-up. The onnx inference backend is required
on the Pi's Python 3.13 (no tflite-runtime wheel exists there).
"""

import numpy as np
from openwakeword.model import Model

import config


class WakeWord:
    # openWakeWord expects 16 kHz audio in 1280-sample (80 ms) chunks.
    FRAME_LENGTH = 1280
    SAMPLE_RATE = 16000

    def __init__(self, model=None, threshold=None):
        if model is not None:
            self.model_ref, self.is_custom = model, False
        elif config.WAKEWORD_MODEL.exists():
            self.model_ref, self.is_custom = str(config.WAKEWORD_MODEL), True
        else:
            self.model_ref, self.is_custom = config.WAKEWORD_PRETRAINED, False

        self.threshold = (
            threshold if threshold is not None else config.WAKEWORD_THRESHOLD
        )
        self._model = Model(
            wakeword_models=[self.model_ref], inference_framework="onnx"
        )

    @property
    def label(self):
        return (
            "custom Hey-Leofric"
            if self.is_custom
            else f"pretrained '{self.model_ref}'"
        )

    def process(self, frame_bytes):
        """Feed one audio frame; return (detected: bool, best_score: float)."""
        pcm = np.frombuffer(frame_bytes, dtype=np.int16)
        scores = self._model.predict(pcm)
        best = max(scores.values()) if scores else 0.0
        return best >= self.threshold, float(best)
