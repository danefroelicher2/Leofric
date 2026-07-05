"""
scripts/list_audio.py — enumerate audio input devices as PyAudio/PortAudio sees them.

Phase 1H bring-up diagnostic: shows the ReSpeaker's device index, channel count,
and default sample rate, and whether it can open a 16 kHz mono stream (what the
wake-word engine needs). Run before writing/using the microphone code.

Usage (venv active, from project root):
    python scripts/list_audio.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyaudio  # noqa: E402

import config  # noqa: E402


def main():
    pa = pyaudio.PyAudio()
    try:
        try:
            default_in = pa.get_default_input_device_info()["name"]
        except Exception:
            default_in = "(none)"
        print(f"Default input device: {default_in}\n")

        print("Input-capable devices:")
        respeaker_indices = []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info["maxInputChannels"] <= 0:
                continue
            name = info["name"]
            print(
                f"  [{i}] {name!r}  in_channels={info['maxInputChannels']}  "
                f"default_rate={int(info['defaultSampleRate'])}"
            )
            if config.AUDIO_DEVICE_NAME.lower() in name.lower():
                respeaker_indices.append(i)

        print()
        if not respeaker_indices:
            print(f"!! No device matching {config.AUDIO_DEVICE_NAME!r} found.")
            return

        for idx in respeaker_indices:
            info = pa.get_device_info_by_index(idx)
            print(f"ReSpeaker match at index {idx}: {info['name']!r}")
            for ch in (1, info["maxInputChannels"]):
                try:
                    ok = pa.is_format_supported(
                        16000,
                        input_device=idx,
                        input_channels=int(ch),
                        input_format=pyaudio.paInt16,
                    )
                except Exception as e:
                    ok = f"no ({e})"
                print(f"  16kHz int16, {int(ch)} channel(s): {ok}")
    finally:
        pa.terminate()


if __name__ == "__main__":
    main()
