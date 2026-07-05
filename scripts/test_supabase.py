"""
scripts/test_supabase.py — Phase 1G: write a test event and read it back.

Confirms the Pi can reach Supabase and that the events table + credentials work,
by inserting one dummy event and then reading the most recent events back.

Usage (venv active, from project root):
    python scripts/test_supabase.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.events import EventStore  # noqa: E402


def main():
    store = EventStore()
    print("Inserting a test event...")
    store.log_event("test", {"note": "hello from leofric", "phase": "1G"})

    print("Most recent events in Supabase:")
    for row in store.recent_events():
        print(f"  [{row['created_at']}] {row['event_type']} -> {row['metadata']}")
    print("If you see the test event above (and in the Supabase dashboard), 1G works.")


if __name__ == "__main__":
    main()
