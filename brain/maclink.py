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
import time

import requests

import config

logger = logging.getLogger(__name__)


class MacLink:
    RETRY_AFTER_SECONDS = 30  # after a failure, skip the Mac this long (circuit open)

    def __init__(self, base_url=None, node_id=None, timeout=(1.5, 2)):
        base = (base_url or config.MAC_MINI_URL).rstrip("/")
        node = node_id or config.NODE_ID
        self.url = f"{base}/ingest/event/{node}"
        self.timeout = timeout
        self._session = requests.Session()
        self._connected = None  # tri-state so first success/failure both log once
        self._skip_until = 0.0  # circuit-breaker: skip HTTP until this time

    def send_event(self, event_type, metadata=None):
        """POST one event; return the Mac's snapshot_id (or None). Never raises,
        and while the Mac is unreachable it stalls the caller for at most one
        probe per RETRY_AFTER_SECONDS (circuit breaker) — the vision loop must
        never block on a dead Mac."""
        if time.time() < self._skip_until:
            return None  # Mac known-down; don't block the loop re-probing it
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
            self._skip_until = 0.0
            return resp.json().get("snapshot_id")
        except Exception as e:
            self._skip_until = time.time() + self.RETRY_AFTER_SECONDS
            if self._connected is not False:
                self._connected = False
                logger.warning("Event link to the Mac is down: %s", e)
            return None
