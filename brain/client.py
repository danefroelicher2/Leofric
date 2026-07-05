"""
brain/client.py — HTTP client to the Mac Mini brain.

POSTs transcribed text (plus recent conversation) to the Mac Mini's Flask API and
returns Leofric's text reply. The Mac Mini runs the heavy LLM (Ollama / Llama 3.2);
the Pi stays light. Network failures raise BrainError so the caller can decide how
to handle them (log, retry) rather than crashing the always-on loop.
"""

import requests

import config


class BrainError(Exception):
    pass


class BrainClient:
    def __init__(self, base_url=None, timeout=120):
        self.base_url = (base_url or config.MAC_MINI_URL).rstrip("/")
        self.timeout = timeout

    def chat(self, message, history=None):
        """Send a message (+ optional history) to the brain; return its reply text."""
        try:
            resp = requests.post(
                f"{self.base_url}/chat",
                json={"message": message, "history": history or []},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except requests.RequestException as e:
            raise BrainError(f"brain request failed: {e}") from e

    def health(self):
        """Return True if the brain API is reachable."""
        try:
            return requests.get(f"{self.base_url}/", timeout=5).ok
        except requests.RequestException:
            return False
