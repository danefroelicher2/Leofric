"""Unit tests for the notification decision engine. Run:
    ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_notify -v
"""

import unittest

from macmini import notify


class BuildAlertTest(unittest.TestCase):
    def test_identity_known_person(self):
        alert = notify.build_alert("identity", {"name": "dane"}, "front-door")
        self.assertEqual(alert["title"], "Leofric")
        self.assertIn("Dane", alert["body"])
        self.assertIn("front-door", alert["body"])
        self.assertFalse(alert["unknown"])

    def test_identity_unknown_person(self):
        alert = notify.build_alert("identity", {"name": "unknown"}, "front-door")
        self.assertIn("UNKNOWN PERSON", alert["body"])
        self.assertTrue(alert["unknown"])

    def test_person_without_identity_is_unknown(self):
        alert = notify.build_alert("person", {"count": 1}, "front-door")
        self.assertTrue(alert["unknown"])
        self.assertIn("UNKNOWN PERSON", alert["body"])

    def test_motion_never_notifies(self):
        self.assertIsNone(notify.build_alert("motion", {"area": 5000}, "front-door"))


class ShouldSendTest(unittest.TestCase):
    def test_security_node_known_person_sends(self):
        last = {}
        self.assertTrue(notify.should_send("identity", "security", False, "d", 1000.0, last))
        self.assertEqual(last["d"], 1000.0)

    def test_assistant_node_never_sends(self):
        self.assertFalse(notify.should_send("identity", "assistant", False, "lr", 1000.0, {}))

    def test_none_role_treated_as_security(self):
        # A node whose role we don't know yet defaults to notifying (fail-safe:
        # better a spurious alert than a missed intruder).
        self.assertTrue(notify.should_send("identity", None, False, "d", 1000.0, {}))

    def test_cooldown_blocks_repeat_known_person(self):
        last = {"d": 1000.0}
        self.assertFalse(notify.should_send("identity", "security", False, "d", 1030.0, last))
        self.assertTrue(notify.should_send("identity", "security", False, "d", 1061.0, last))

    def test_unknown_always_sends_even_within_cooldown(self):
        last = {"d": 1000.0}
        self.assertTrue(notify.should_send("identity", "security", True, "d", 1005.0, last))

    def test_cooldown_is_per_node(self):
        last = {"a": 1000.0}
        self.assertTrue(notify.should_send("identity", "security", False, "b", 1005.0, last))


if __name__ == "__main__":
    unittest.main()
