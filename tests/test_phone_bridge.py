import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from adblite.phone_bridge import PhoneBridgeServer


class PhoneBridgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.bridge = PhoneBridgeServer(Path(self.directory.name), bind_host="127.0.0.1", port=0)
        self.bridge.start()

    def tearDown(self):
        self.bridge.stop()
        self.directory.cleanup()

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.bridge.port}{path}"

    def _authorized(self, path: str) -> str:
        return self._url(path) + ("&" if "?" in path else "?") + "token=" + self.bridge.token

    def test_page_requires_token_and_state_is_authenticated(self):
        with self.assertRaises(HTTPError) as context:
            urlopen(self._url("/"), timeout=2)
        self.assertEqual(context.exception.code, 401)

        self.bridge.write_text("hello")
        response = urlopen(self._authorized("/api/state"), timeout=2)
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["text"], "hello")

    def test_send_appends_received_message(self):
        body = json.dumps({"text": "from phone"}).encode("utf-8")
        request = Request(
            self._url("/api/send"),
            data=body,
            headers={"Authorization": f"Bearer {self.bridge.token}", "Content-Type": "application/json"},
            method="POST",
        )
        response = urlopen(request, timeout=2)
        self.assertEqual(json.loads(response.read().decode("utf-8"))["message"], "已收到（10 字）")
        self.assertIn("from phone", self.bridge.read_received())

    def test_custom_token_is_used_instead_of_generated_value(self):
        self.bridge.stop()
        self.bridge = PhoneBridgeServer(Path(self.directory.name), bind_host="127.0.0.1", port=0, access_token="123456")
        self.bridge.start()
        self.assertEqual(self.bridge.token, "123456")
        response = urlopen(self._authorized("/api/state"), timeout=2)
        self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main()
