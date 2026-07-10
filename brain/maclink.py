"""
brain/maclink.py — best-effort event push from the Pi to the Mac (Phase 2B).

Events already flow to Supabase for durable history (storage/events.py). This
second channel exists for *speed*: the Mac hears about a person at the door in
under a second — soon the trigger for push notifications — and photographs the
moment by pairing the event with the freshest frame it already holds, returning
a snapshot_id the caller stores in the event's Supabase metadata.

Same resilience contract as vision/streamer.py: if the Mac is down, log the
state change once and carry on. The vision loop never depends on this call.
"""

import logging

import requests

import config

logger = logging.getLogger(__name__)


class MacLink:
    def __init__(self, base_url=None, node_id=None, timeout=3):
        base = (base_url or config.MAC_MINI_URL).rstrip("/")
        node = node_id or config.NODE_ID
        self.url = f"{base}/ingest/event/{node}"
        self.timeout = timeout
        self._session = requests.Session()
        self._connected = None  # tri-state so first success/failure both log once

    def send_event(self, event_type, metadata=None):
        """POST one event; return the Mac's snapshot_id (or None). Never raises."""
        try:
            resp = self._session.post(
                self.url,
                json={"event_type": event_type, "metadata": metadata or {}},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            if self._connected is not True:
                self._connected = True
                logger.info("Event link to the Mac is up.")
            return resp.json().get("snapshot_id")
        except Exception as e:
            if self._connected is not False:
                self._connected = False
                logger.warning("Event link to the Mac is down: %s", e)
            return None
