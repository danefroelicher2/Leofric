"""
audio/wakeword.py — wake-word detection with openWakeWord.

openWakeWord is an offline, on-device keyword spotter — our replacement for
Porcupine (see docs/DECISIONS.md ADR-003). A small shared feature extractor
(mel-spectrogram + embedding) feeds lightweight per-keyword models. We hand it
16 kHz int16 audio in ~80 ms chunks; predict() returns a score 0..1 per model and
we fire when the best score crosses a threshold.

Uses the custom "Hey Leofric" model (data/models/hey_leofric.onnx) if present,
otherwise a pretrained model for bring-up. The onnx inference backend is required
on the Pi's Python 3.13 (no tflite-runtime wheel exists there); openWakeWord 0.6.0
ships the pretrained models as bundled .onnx files.
"""

from pathlib import Path

import numpy as np
import openwakeword
from openwakeword.model import Model

import config


def _resolve_pretrained_path(name: str) -> str:
    """Map a pretrained keyword name (e.g. 'hey_jarvis') to its bundled .onnx path."""
    for path in openwakeword.get_pretrained_model_paths():
        if Path(path).name.startswith(name):
            return path
    available = [Path(p).name.split("_v")[0] for p in openwakeword.get_pretrained_model_paths()]
    raise RuntimeError(
        f"Pretrained wake word {name!r} not found. Available: {available}"
    )


class WakeWord:
    # openWakeWord expects 16 kHz audio in 1280-sample (80 ms) chunks.
    FRAME_LENGTH = 1280
    SAMPLE_RATE = 16000

    def __init__(self, model_path=None, threshold=None):
        if model_path is not None:
            self.model_path, self.is_custom = str(model_path), False
        elif config.WAKEWORD_MODEL.exists():
            self.model_path, self.is_custom = str(config.WAKEWORD_MODEL), True
        else:
            self.model_path = _resolve_pretrained_path(config.WAKEWORD_PRETRAINED)
            self.is_custom = False

        self.threshold = (
            threshold if threshold is not None else config.WAKEWORD_THRESHOLD
        )
        # wakeword_model_paths takes file paths. openWakeWord 0.6.0 is ONNX-native
        # (the preprocessor defaults to its .onnx feature models), so we pass no
        # framework flag — it is inferred from the .onnx model files.
        self._model = Model(wakeword_model_paths=[self.model_path])

    @property
    def label(self):
        if self.is_custom:
            return "custom Hey-Leofric"
        return f"pretrained '{Path(self.model_path).name.split('_v')[0]}'"

    def process(self, frame_bytes):
        """Feed one audio frame; return (detected: bool, best_score: float)."""
        pcm = np.frombuffer(frame_bytes, dtype=np.int16)
        scores = self._model.predict(pcm)
        best = max(scores.values()) if scores else 0.0
        return best >= self.threshold, float(best)
