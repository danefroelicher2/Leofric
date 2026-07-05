"""
storage/events.py — persistent event + conversation logging to Supabase.

The Pi is a trusted backend, so it authenticates with the service_role key (kept
in .env, never committed). Row Level Security is enabled on the tables: the
service_role key bypasses it, while the public anon key cannot touch the data.

Events are small structured records; anything richer goes in the `metadata` JSON
column so we can add fields later without a schema migration. Logging must never
take down the main loop, so write failures (a network blip, Supabase down) are
caught and logged rather than raised.
"""

import logging

from supabase import Client, create_client

import config

logger = logging.getLogger(__name__)


class EventStore:
    def __init__(self):
        self._client: Client = create_client(
            config.supabase_url(), config.supabase_key()
        )

    def log_event(self, event_type, metadata=None, node_id=None):
        """Record one event (e.g. 'motion', 'person', 'identity')."""
        row = {
            "node_id": node_id or config.NODE_ID,
            "event_type": event_type,
            "metadata": metadata or {},
        }
        try:
            self._client.table("events").insert(row).execute()
        except Exception as e:  # never let logging crash the pipeline
            logger.warning("Failed to log event %r: %s", event_type, e)

    def log_conversation(self, role, content, session_id=None, node_id=None):
        """Record one line of conversation (role='user' or 'leofric')."""
        row = {
            "node_id": node_id or config.NODE_ID,
            "session_id": session_id,
            "role": role,
            "content": content,
        }
        try:
            self._client.table("conversations").insert(row).execute()
        except Exception as e:
            logger.warning("Failed to log conversation: %s", e)

    def recent_events(self, limit=5):
        """Return the most recent events (used for verification/debugging)."""
        resp = (
            self._client.table("events")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data
