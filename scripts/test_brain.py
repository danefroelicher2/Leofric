"""
scripts/test_brain.py — Phase 1J: talk to the Mac Mini brain over HTTP.

Checks the brain is reachable, then holds a short typed conversation from the
terminal (no voice yet) so we can confirm the Pi -> Mac Mini -> Ollama -> Pi path
works and that conversation context carries across turns.

Usage (venv active, from project root):
    python scripts/test_brain.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from log import setup_logging  # noqa: E402
from brain.client import BrainClient, BrainError  # noqa: E402
from brain.conversation import Conversation  # noqa: E402

logger = logging.getLogger("test_brain")


def main():
    setup_logging()
    client = BrainClient()
    logger.info("Brain URL: %s", config.MAC_MINI_URL)
    if not client.health():
        logger.error("Brain not reachable at %s — is server.py running?", config.MAC_MINI_URL)
        return
    logger.info("Brain is reachable. Type a message (or 'quit').")

    convo = Conversation()
    while True:
        try:
            message = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not message or message.lower() in {"quit", "exit"}:
            break
        convo.add("user", message)
        try:
            reply = client.chat(message, history=convo.history())
        except BrainError as e:
            logger.error("%s", e)
            continue
        convo.add("assistant", reply)
        print(f"leofric > {reply}")


if __name__ == "__main__":
    main()
