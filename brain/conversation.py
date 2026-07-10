"""
brain/conversation.py — in-session conversation memory.

Holds the recent turns so Leofric has short-term context within a session, bounded
to the last N turns to keep the prompt small. Persistent, cross-session history
lives in Supabase (storage/events.log_conversation); this is just the working set
sent to the brain with each request. Sessions rotate after an idle gap: each
wake-word conversation is one session_id, which the app renders as one chat thread.
"""

import time


class Conversation:
    def __init__(self, max_turns=12, node_id="leofric", idle_seconds=180):
        self.max_turns = max_turns
        self.node_id = node_id
        self.idle_seconds = idle_seconds
        self._turns = []  # list of {"role": "user"|"assistant", "content": str}
        self._session_id = None
        self._last_at = 0.0

    def begin_exchange(self, now=None):
        """Call at the start of each user utterance. A pause longer than
        idle_seconds means a new conversation: fresh session id (= a new chat
        thread in the app) and cleared short-term context."""
        now = time.time() if now is None else now
        if self._session_id is None or now - self._last_at > self.idle_seconds:
            self._session_id = f"{self.node_id}-{int(now)}"
            self._turns = []
        self._last_at = now
        return self._session_id

    def add(self, role, content):
        self._turns.append({"role": role, "content": content})
        if len(self._turns) > self.max_turns:
            self._turns = self._turns[-self.max_turns :]

    def history(self):
        return list(self._turns)

    def clear(self):
        self._turns = []
