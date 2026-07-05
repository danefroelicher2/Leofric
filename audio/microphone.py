"""
audio/microphone.py — continuous microphone input from the ReSpeaker.

Opens the ReSpeaker as a 16 kHz mono int16 stream (confirmed supported by the
device via scripts/list_audio.py) — the format the wake-word engine and Whisper
both expect. Reads fixed-size frames so the wake-word engine can be fed one chunk
at a time. The device is located by name so USB re-enumeration can't break it.
"""

import pyaudio

import config


class Microphone:
    def __init__(self, rate=16000, channels=1, frame_length=1280, device_name=None):
        self.rate = rate
        self.channels = channels
        self.frame_length = frame_length
        self.device_name = device_name or config.AUDIO_DEVICE_NAME
        self._pa = None
        self._stream = None

    def _find_device_index(self):
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if (
                self.device_name.lower() in info["name"].lower()
                and info["maxInputChannels"] > 0
            ):
                return i
        return None

    def start(self):
        self._pa = pyaudio.PyAudio()
        idx = self._find_device_index()
        if idx is None:
            names = [
                self._pa.get_device_info_by_index(i)["name"]
                for i in range(self._pa.get_device_count())
            ]
            self._pa.terminate()
            raise RuntimeError(
                f"Audio device {self.device_name!r} not found. Available: {names}"
            )
        self._stream = self._pa.open(
            rate=self.rate,
            channels=self.channels,
            format=pyaudio.paInt16,
            input=True,
            input_device_index=idx,
            frames_per_buffer=self.frame_length,
        )
        return self

    def read_frame(self):
        """Return one frame of frame_length int16 samples as raw bytes."""
        return self._stream.read(self.frame_length, exception_on_overflow=False)

    def stop(self):
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.stop()
