"""
scripts/measure_audio.py — diagnostic: live microphone RMS meter.

Prints the RMS energy of each mic frame in real time so we can see the actual
gap between "silence" (room ambient noise) and "speech" (you talking). This is
what sets a correct VAD_SILENCE_RMS: the endpointer in audio/transcription.py
treats any frame at or above that value as speech, so the threshold must sit
comfortably ABOVE your room's idle level but BELOW your speaking level.

Run it, then follow the on-screen prompts: stay silent for a few seconds, then
talk normally, and watch the numbers. Ctrl+C to stop. It also prints a running
summary (min/median/max seen) at the end.

Usage (venv active, from project root):
    python scripts/measure_audio.py
"""

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from audio.microphone import Microphone  # noqa: E402


def rms(frame_bytes):
    samples = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples**2)))


def bar(value, scale=4000.0, width=50):
    filled = min(width, int(width * value / scale))
    return "#" * filled + "-" * (width - filled)


def main():
    mic = Microphone()  # 16 kHz mono, 1280-sample frames (0.08s each)
    print(f"Current config VAD_SILENCE_RMS = {config.VAD_SILENCE_RMS}")
    print("Opening mic. Be SILENT for ~5s, then TALK normally. Ctrl+C to stop.\n")

    seen = []
    with mic:
        try:
            while True:
                value = rms(mic.read_frame())
                seen.append(value)
                marker = "  <-- above threshold (counts as SPEECH)" if value >= config.VAD_SILENCE_RMS else ""
                print(f"RMS {value:7.0f} |{bar(value)}|{marker}")
                time.sleep(0.0)  # frames already pace us at ~12.5/sec
        except KeyboardInterrupt:
            pass

    if seen:
        arr = np.array(seen)
        print("\n--- summary ---")
        print(f"frames:  {arr.size}")
        print(f"min:     {arr.min():.0f}   (quietest — near your room's true silence)")
        print(f"median:  {np.median(arr):.0f}")
        print(f"max:     {arr.max():.0f}   (loudest — near your speaking peaks)")
        print(f"\nPick VAD_SILENCE_RMS between the silent level and the speech level.")


if __name__ == "__main__":
    main()
