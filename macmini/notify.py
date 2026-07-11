"""
macmini/notify.py — pure notification decision logic (no I/O).

Separated from APNs sending and the Flask route so the "should we notify, and
what does it say" rules are unit-testable without a network or credentials.
"""

COOLDOWN_SECONDS = 60
NOTIFY_EVENT_TYPES = {"person", "identity"}


def build_alert(event_type, metadata, node):
    """Return {title, body, unknown} for a notifiable event, else None.

    A 'person' event (motion that resolved to a human but no face match) and an
    'identity' event with name 'unknown' both count as an unknown person — the
    loud case. A named identity is the calm case. Motion never notifies.
    """
    if event_type not in NOTIFY_EVENT_TYPES:
        return None
    name = (metadata or {}).get("name")
    unknown = event_type == "person" or not name or name == "unknown"
    if unknown:
        body = f"UNKNOWN PERSON at {node}"
    else:
        body = f"{name.capitalize()} at {node}"
    return {"title": "Leofric", "body": body, "unknown": unknown}


def should_send(event_type, role, unknown, node, now, last_sent):
    """Apply the notify rules; record the send time in last_sent on a True.

    Rules: only 'person'/'identity' at a security node (role None is treated
    as security — fail toward alerting); unknown persons always alert; known
    persons are rate-limited to one per COOLDOWN_SECONDS per node.
    """
    if event_type not in NOTIFY_EVENT_TYPES:
        return False
    if role == "assistant":
        return False
    if not unknown:
        previous = last_sent.get(node)
        if previous is not None and now - previous < COOLDOWN_SECONDS:
            return False
    last_sent[node] = now
    return True
