import unittest

from bot import version
from bot.main import ping_text


class VersionTest(unittest.TestCase):
    def test_project_version_is_1_0(self):
        self.assertEqual(version.__version__, "1.0")

    def test_ping_text_includes_project_version(self):
        self.assertEqual(ping_text(), "pong v1.0")


if __name__ == "__main__":
    unittest.main()
