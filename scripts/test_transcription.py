"""
scripts/test_transcription.py — Phase 1I test.

Listens for the wake word; when it fires, records what you say next (until you
pause), transcribes it locally with faster-whisper, and logs the text. Then it
goes back to listening. Ctrl+C to stop.

Say the wake word ('Hey Jarvis' for now), then a sentence — e.g.
"Hey Jarvis ... what time is it".

First run downloads the Whisper model (needs internet, one time).

Usage (venv active, from project root):
    python scripts/test_transcription.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from log import setup_logging  # noqa: E402
from audio.microphone import Microphone  # noqa: E402
from audio.transcription import Transcriber, record_utterance  # noqa: E402
from audio.wakeword import WakeWord  # noqa: E402

logger = logging.getLogger("test_transcription")


def main():
    setup_logging()
    ww = WakeWord()
    logger.info("Loading Whisper model %r (first run downloads it)...", config.WHISPER_MODEL)
    transcriber = Transcriber()
    mic = Microphone(
        rate=WakeWord.SAMPLE_RATE, channels=1, frame_length=WakeWord.FRAME_LENGTH
    )

    logger.info(
        "Ready. Say the wake word (%s) then a sentence. Ctrl+C to stop.", ww.label
    )
    with mic:
        try:
            while True:
                detected, score = ww.process(mic.read_frame())
                if not detected:
                    continue
                logger.info("Wake word (score=%.2f) — listening, speak now...", score)
                audio = record_utterance(mic)
                text = transcriber.transcribe(audio)
                if text:
                    logger.info('You said: "%s"', text)
                else:
                    logger.info("(no speech transcribed)")
                logger.info("Back to listening for the wake word...")
        except KeyboardInterrupt:
            logger.info("Stopped.")


if __name__ == "__main__":
    main()
