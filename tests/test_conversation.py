"""Unit tests for brain/conversation.py session rotation:
    ~/leofric-brain/venv/bin/python3 -m unittest tests.test_conversation -v
"""

import unittest

from brain.conversation import Conversation


class SessionTest(unittest.TestCase):
    def test_same_session_within_idle_window(self):
        convo = Conversation(node_id="leofric", idle_seconds=180)
        first = convo.begin_exchange(now=1000.0)
        second = convo.begin_exchange(now=1100.0)  # 100s later — same session
        self.assertEqual(first, second)
        self.assertEqual(first, "leofric-1000")

    def test_idle_gap_rotates_session_and_clears_context(self):
        convo = Conversation(node_id="leofric", idle_seconds=180)
        convo.begin_exchange(now=1000.0)
        convo.add("user", "hello")
        rotated = convo.begin_exchange(now=1300.0)  # 300s later — new session
        self.assertEqual(rotated, "leofric-1300")
        self.assertEqual(convo.history(), [])

    def test_history_survives_within_a_session(self):
        convo = Conversation(node_id="leofric", idle_seconds=180)
        convo.begin_exchange(now=1000.0)
        convo.add("user", "hello")
        convo.begin_exchange(now=1050.0)
        self.assertEqual(len(convo.history()), 1)


if __name__ == "__main__":
    unittest.main()
