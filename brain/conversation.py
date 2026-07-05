"""
brain/conversation.py — in-session conversation memory.

Holds the recent turns so Leofric has short-term context within a session, bounded
to the last N turns to keep the prompt small. Persistent, cross-session history
lives in Supabase (storage/events.log_conversation); this is just the working set
sent to the brain with each request.
"""


class Conversation:
    def __init__(self, max_turns=12):
        self.max_turns = max_turns
        self._turns = []  # list of {"role": "user"|"assistant", "content": str}

    def add(self, role, content):
        self._turns.append({"role": role, "content": content})
        if len(self._turns) > self.max_turns:
            self._turns = self._turns[-self.max_turns :]

    def history(self):
        return list(self._turns)

    def clear(self):
        self._turns = []
