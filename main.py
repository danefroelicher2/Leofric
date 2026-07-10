"""
main.py — Leofric entry point.

Starts every subsystem as a thread and runs until stopped (Ctrl+C or systemd).
Two workers run concurrently:

  VisionWorker: camera -> motion -> person -> identity. Motion is the cheap
    trigger; person (DNN) runs only on motion frames, and identity (face) only
    when a person is present. Distinct events are logged to Supabase.

  AudioWorker : wake word -> record utterance -> transcribe (Whisper) -> brain
    (Mac Mini LLM) -> reply. Each turn is logged to the conversations table.

Both log to console + rotating file (log.py) and, best-effort, to Supabase.
Designed to run continuously as an always-on process.
"""

import logging
import signal
import threading
import time

import config
from log import setup_logging
from storage.events import EventStore
from vision.camera import Camera
from vision.motion import MotionDetector
from vision.person import PersonDetector
from vision.identity import IdentityRecognizer
from vision.streamer import FrameStreamer
from audio.microphone import Microphone
from audio.wakeword import WakeWord
from audio.transcription import Transcriber, record_utterance
from brain.client import BrainClient, BrainError
from brain.maclink import MacLink
from brain.conversation import Conversation

logger = logging.getLogger("leofric")


class VisionWorker(threading.Thread):
    """Camera pipeline: motion gates person gates identity; logs distinct events."""

    MOTION_CLEAR_SECONDS = 2.0
    PERSON_CHECK_INTERVAL = 0.5
    IDENTITY_INTERVAL = 3.0

    def __init__(self, store, stop_event):
        super().__init__(name="vision", daemon=True)
        self.store = store
        self.stop_event = stop_event
        self.camera = Camera()
        self.motion = MotionDetector()
        self.person = PersonDetector()
        self.identity = IdentityRecognizer()
        self.maclink = MacLink()

    def _log_event(self, event_type, metadata):
        """Fast path to the Mac (returns snapshot_id if it photographed the
        moment), then the durable path to Supabase with that id attached."""
        snapshot_id = self.maclink.send_event(event_type, metadata)
        if snapshot_id:
            metadata = dict(metadata, snapshot_id=snapshot_id)
        self.store.log_event(event_type, metadata)

    def run(self):
        self.camera.start()
        logger.info("Vision online.")
        motion_active = False
        last_motion_at = 0.0
        person_present = False
        last_person_check = 0.0
        last_identity_at = 0.0
        try:
            while not self.stop_event.is_set():
                frame = self.camera.read()
                if frame is None:
                    time.sleep(0.05)
                    continue
                now = time.time()
                m = self.motion.process(frame)

                if m.detected:
                    last_motion_at = now
                    if not motion_active:
                        motion_active = True
                        logger.info("motion (area=%d)", m.total_area)
                        self._log_event("motion", {"area": m.total_area})
                elif motion_active and now - last_motion_at > self.MOTION_CLEAR_SECONDS:
                    motion_active = False

                # Person (costly) only on motion frames, throttled.
                if m.detected and now - last_person_check >= self.PERSON_CHECK_INTERVAL:
                    last_person_check = now
                    p = self.person.process(frame)
                    if p.detected:
                        if not person_present:
                            person_present = True
                            logger.info("person detected (%d)", len(p.boxes))
                            self._log_event("person", {"count": len(p.boxes)})
                        # Identity (face) only while a person is present, throttled.
                        if now - last_identity_at >= self.IDENTITY_INTERVAL:
                            last_identity_at = now
                            for f in self.identity.classify(frame):
                                logger.info("identity: %s (%.2f)", f.name, f.similarity)
                                self._log_event(
                                    "identity",
                                    {"name": f.name, "similarity": round(f.similarity, 3)},
                                )
                    else:
                        person_present = False

                time.sleep(0.02)
        except Exception:
            logger.exception("Vision worker crashed")
        finally:
            self.camera.stop()
            logger.info("Vision stopped.")


class AudioWorker(threading.Thread):
    """Audio pipeline: wake word -> transcribe -> brain -> reply; logs conversation."""

    def __init__(self, store, stop_event):
        super().__init__(name="audio", daemon=True)
        self.store = store
        self.stop_event = stop_event
        self.wakeword = WakeWord()
        self.transcriber = Transcriber()
        self.mic = Microphone(
            rate=WakeWord.SAMPLE_RATE, channels=1, frame_length=WakeWord.FRAME_LENGTH
        )
        self.brain = BrainClient()
        self.convo = Conversation(
            node_id=config.NODE_ID, idle_seconds=config.SESSION_IDLE_SECONDS
        )

    def run(self):
        self.mic.start()
        logger.info("Audio online. Wake word: %s", self.wakeword.label)
        try:
            while not self.stop_event.is_set():
                detected, score = self.wakeword.process(self.mic.read_frame())
                if not detected:
                    continue
                logger.info("wake word (%.2f) — listening", score)
                text = self.transcriber.transcribe(record_utterance(self.mic))
                if not text:
                    logger.info("(no speech transcribed)")
                    continue
                logger.info("heard: %s", text)
                session_id = self.convo.begin_exchange()
                self.convo.add("user", text)
                self.store.log_conversation("user", text, session_id=session_id)
                try:
                    reply = self.brain.chat(text, history=self.convo.history())
                except BrainError as e:
                    logger.warning("brain unreachable: %s", e)
                    continue
                self.convo.add("assistant", reply)
                self.store.log_conversation("leofric", reply, session_id=session_id)
                logger.info("leofric: %s", reply)
        except Exception:
            logger.exception("Audio worker crashed")
        finally:
            self.mic.stop()
            logger.info("Audio stopped.")


def main():
    setup_logging()
    logger.info("Leofric starting (node=%s)...", config.NODE_ID)
    store = EventStore()
    stop_event = threading.Event()

    def handle_stop(signum, _frame):
        logger.info("Shutdown signal (%s) received.", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    vision = VisionWorker(store, stop_event)
    audio = AudioWorker(store, stop_event)
    vision.start()
    audio.start()
    # Streamer shares the vision worker's camera (one process may own the USB
    # device); it tolerates the camera not being started for the first moments.
    streamer = None
    if config.STREAM_ENABLED:
        streamer = FrameStreamer(vision.camera, stop_event)
        streamer.start()
    logger.info("Leofric online. Ctrl+C to stop.")

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    finally:
        stop_event.set()
        vision.join(timeout=5)
        audio.join(timeout=5)
        if streamer is not None:
            streamer.join(timeout=5)
        logger.info("Leofric stopped.")


if __name__ == "__main__":
    main()
