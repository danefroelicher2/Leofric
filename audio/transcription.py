"""
audio/transcription.py — record an utterance after the wake word and transcribe it.

Two parts:
  1. record_utterance(): after the wake word fires, capture audio from the mic
     until the speaker goes quiet (simple energy-based endpointing) or a max
     duration is reached. There is no fixed recording length — it adapts to how
     long you actually talk.
  2. Transcriber: faster-whisper (CTranslate2) running locally on the Pi. Chosen
     over openai-whisper to avoid the heavy torch stack (see DECISIONS.md ADR-004);
     int8 quantization keeps it fast on the Pi's CPU.
"""

import numpy as np
from faster_whisper import WhisperModel

import config


def _rms(frame_bytes):
    samples = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples**2)))


def record_utterance(mic, silence_rms=None, silence_seconds=None, max_seconds=None):
    """Record from `mic` until the speaker pauses; return float32 audio at 16 kHz.

    Endpointing is energy-based: once speech has started, a run of quiet frames
    longer than `silence_seconds` ends the recording. If speech never crosses the
    threshold (e.g. it is mis-tuned), we still stop at `max_seconds` and return
    whatever was captured, so a bad threshold degrades gracefully.
    """
    silence_rms = silence_rms if silence_rms is not None else config.VAD_SILENCE_RMS
    silence_seconds = silence_seconds or config.UTTERANCE_SILENCE_SECONDS
    max_seconds = max_seconds or config.UTTERANCE_MAX_SECONDS

    frame_secs = mic.frame_length / mic.rate
    silence_frames_needed = int(silence_seconds / frame_secs)
    max_frames = int(max_seconds / frame_secs)

    collected = []
    speech_started = False
    silent_run = 0
    for _ in range(max_frames):
        frame = mic.read_frame()
        collected.append(frame)
        if _rms(frame) >= silence_rms:
            speech_started = True
            silent_run = 0
        elif speech_started:
            silent_run += 1
            if silent_run >= silence_frames_needed:
                break

    audio_bytes = b"".join(collected)
    # faster-whisper wants float32 in [-1, 1] at 16 kHz.
    return np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0


class Transcriber:
    def __init__(self, model_size=None):
        self.model_size = model_size or config.WHISPER_MODEL
        # First construction downloads + caches the CTranslate2 model (needs net).
        self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")

    def transcribe(self, audio):
        """Return the transcribed text for a float32 16 kHz audio array.

        vad_filter runs Silero VAD to drop non-speech regions before decoding.
        Without it, faster-whisper tends to *invent* words from marginal or
        near-silent audio (far-field, off-mic, wake-word echo). With it, weak
        audio comes back empty ("no speech") instead of a hallucinated phrase.
        """
        segments, _info = self._model.transcribe(
            audio, language="en", beam_size=1, vad_filter=True
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
