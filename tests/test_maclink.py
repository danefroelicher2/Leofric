"""Unit tests for brain/maclink.py — run on the Mac with the brain venv:
    ~/leofric-brain/venv/bin/python3 -m unittest tests.test_maclink -v
"""

import sys
import unittest
from unittest import mock

sys.modules.setdefault(
    "config",
    mock.Mock(MAC_MINI_URL="http://mac.test:5000", NODE_ID="leofric"),
)

from brain.maclink import MacLink  # noqa: E402


class MacLinkTest(unittest.TestCase):
    def _link(self):
        return MacLink(base_url="http://mac.test:5000", node_id="leofric")

    def test_send_event_returns_snapshot_id(self):
        link = self._link()
        resp = mock.Mock()
        resp.json.return_value = {"ok": True, "snapshot_id": "leofric-123"}
        resp.raise_for_status.return_value = None
        with mock.patch.object(link._session, "post", return_value=resp) as post:
            result = link.send_event("person", {"count": 1})
        self.assertEqual(result, "leofric-123")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "http://mac.test:5000/ingest/event/leofric")
        self.assertEqual(
            kwargs["json"], {"event_type": "person", "metadata": {"count": 1}}
        )

    def test_send_event_null_snapshot(self):
        link = self._link()
        resp = mock.Mock()
        resp.json.return_value = {"ok": True, "snapshot_id": None}
        resp.raise_for_status.return_value = None
        with mock.patch.object(link._session, "post", return_value=resp):
            self.assertIsNone(link.send_event("motion", {}))

    def test_send_event_swallows_network_errors(self):
        link = self._link()
        with mock.patch.object(link._session, "post", side_effect=OSError("down")):
            self.assertIsNone(link.send_event("person", {"count": 1}))  # no raise


if __name__ == "__main__":
    unittest.main()
