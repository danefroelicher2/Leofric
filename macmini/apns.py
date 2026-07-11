"""
macmini/apns.py — Apple Push Notification service client (token auth).

APNs requires HTTP/2 (httpx) and an ES256-signed JWT (PyJWT) built from the
team's .p8 auth key. This class is credential-driven and self-contained; it is
constructed only when APNs env vars are present (see server.py). Sending is
best-effort — send() never raises, returning False on any failure so a push
problem can never disrupt event ingest.
"""

import time

import httpx
import jwt

_JWT_TTL_SECONDS = 3000  # Apple wants a fresh token every 20-60 min; refresh at 50.


class APNsClient:
    def __init__(self, key_path, key_id, team_id, bundle_id, use_sandbox=True, client=None):
        with open(key_path) as f:
            self._key = f.read()
        self.key_id = key_id
        self.team_id = team_id
        self.bundle_id = bundle_id
        host = "api.sandbox.push.apple.com" if use_sandbox else "api.push.apple.com"
        self._base = f"https://{host}"
        self._client = client or httpx.Client(http2=True, timeout=10)
        self._jwt = None
        self._jwt_at = 0.0

    def _build_jwt(self):
        now = time.time()
        if self._jwt is None or now - self._jwt_at > _JWT_TTL_SECONDS:
            self._jwt = jwt.encode(
                {"iss": self.team_id, "iat": int(now)},
                self._key,
                algorithm="ES256",
                headers={"kid": self.key_id},
            )
            self._jwt_at = now
        return self._jwt

    def _payload(self, title, body, snapshot_id, mutable):
        aps = {"alert": {"title": title, "body": body}, "sound": "default"}
        if mutable:
            aps["mutable-content"] = 1
        payload = {"aps": aps}
        if snapshot_id:
            payload["snapshot_id"] = snapshot_id
        return payload

    def send(self, token, title, body, snapshot_id, mutable):
        """POST one notification. Returns True on APNs 200, else False. Never raises."""
        try:
            resp = self._client.post(
                f"{self._base}/3/device/{token}",
                json=self._payload(title, body, snapshot_id, mutable),
                headers={
                    "authorization": f"bearer {self._build_jwt()}",
                    "apns-topic": self.bundle_id,
                    "apns-push-type": "alert",
                    "apns-priority": "10",
                },
            )
            return resp.status_code == 200
        except Exception:
            return False
