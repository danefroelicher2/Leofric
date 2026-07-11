"""Unit tests for the APNs client. Run:
    ~/leofric-brain/venv/bin/python3 -m unittest macmini.test_apns -v
Uses a locally-generated throwaway ES256 key — no real Apple credentials.
"""

import os
import tempfile
import unittest

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from macmini.apns import APNsClient


def _write_test_p8(path):
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with open(path, "wb") as f:
        f.write(pem)
    return key.public_key()


class APNsClientTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.key_path = os.path.join(self.tmp.name, "key.p8")
        self.public_key = _write_test_p8(self.key_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _client(self, transport):
        http = httpx.Client(transport=transport)
        return APNsClient(
            key_path=self.key_path, key_id="KEY123", team_id="TEAM123",
            bundle_id="com.danefroelicher.Leofric", use_sandbox=True, client=http,
        )

    def test_jwt_is_valid_es256_with_headers_and_claims(self):
        client = self._client(httpx.MockTransport(lambda r: httpx.Response(200)))
        token = client._build_jwt()
        header = jwt.get_unverified_header(token)
        self.assertEqual(header["alg"], "ES256")
        self.assertEqual(header["kid"], "KEY123")
        decoded = jwt.decode(token, self.public_key, algorithms=["ES256"])
        self.assertEqual(decoded["iss"], "TEAM123")
        self.assertIn("iat", decoded)

    def test_payload_shape(self):
        client = self._client(httpx.MockTransport(lambda r: httpx.Response(200)))
        payload = client._payload("Leofric", "UNKNOWN PERSON at door", "leofric-1", True)
        self.assertEqual(payload["aps"]["alert"]["title"], "Leofric")
        self.assertEqual(payload["aps"]["alert"]["body"], "UNKNOWN PERSON at door")
        self.assertEqual(payload["aps"]["mutable-content"], 1)
        self.assertEqual(payload["snapshot_id"], "leofric-1")

    def test_send_success_returns_true_and_hits_correct_url(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["topic"] = request.headers.get("apns-topic")
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(200)

        client = self._client(httpx.MockTransport(handler))
        ok = client.send("devtoken123", "Leofric", "Dane at door", "leofric-1", True)
        self.assertTrue(ok)
        self.assertEqual(seen["url"], "https://api.sandbox.push.apple.com/3/device/devtoken123")
        self.assertEqual(seen["topic"], "com.danefroelicher.Leofric")
        self.assertTrue(seen["auth"].startswith("bearer "))

    def test_send_uses_production_host_when_not_sandbox(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            return httpx.Response(200)

        http = httpx.Client(transport=httpx.MockTransport(handler))
        client = APNsClient(
            key_path=self.key_path, key_id="K", team_id="T",
            bundle_id="com.danefroelicher.Leofric", use_sandbox=False, client=http,
        )
        client.send("tok", "t", "b", None, False)
        self.assertTrue(seen["url"].startswith("https://api.push.apple.com/"))

    def test_send_non_200_returns_false(self):
        client = self._client(httpx.MockTransport(lambda r: httpx.Response(410)))
        self.assertFalse(client.send("tok", "t", "b", None, False))

    def test_send_never_raises_on_transport_error(self):
        def boom(request):
            raise httpx.ConnectError("down")

        client = self._client(httpx.MockTransport(boom))
        self.assertFalse(client.send("tok", "t", "b", None, False))
