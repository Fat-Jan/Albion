import socket
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from bot.main import _configured_health_port, start_health_server_if_configured


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class HealthServerTest(unittest.TestCase):
    def test_no_health_port_by_default(self):
        with patch.dict("os.environ", {"HEALTH_PORT": "", "PORT": ""}, clear=False):
            self.assertIsNone(_configured_health_port())
            self.assertIsNone(start_health_server_if_configured())

    def test_health_endpoint_responds_when_port_configured(self):
        port = _free_port()
        with patch.dict("os.environ", {"HEALTH_PORT": str(port), "PORT": ""}, clear=False):
            server = start_health_server_if_configured()
        self.assertIsNotNone(server)
        try:
            with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"ok\n")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
