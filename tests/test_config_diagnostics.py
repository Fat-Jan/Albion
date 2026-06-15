import hashlib
import unittest

from bot import config


class ConfigDiagnosticsTest(unittest.TestCase):
    def test_token_runtime_info_reports_bot_id_and_fingerprint_without_secret(self):
        token = "1/MTIzNDU=/super-secret-value"

        info = config.token_runtime_info(token)

        self.assertEqual(info["bot_id"], "12345")
        self.assertEqual(
            info["fingerprint"], hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
        )
        self.assertNotIn("super-secret-value", info.values())

    def test_token_runtime_info_marks_environment_override(self):
        info = config.token_runtime_info(
            "1/MTIzNDU=/from-shell",
            env_file_token="1/MTIzNDU=/from-env-file",
        )

        self.assertEqual(info["source"], "environment_overrides_env_file")

    def test_token_runtime_info_marks_env_file_source_when_values_match(self):
        token = "1/MTIzNDU=/same"

        info = config.token_runtime_info(token, env_file_token=token)

        self.assertEqual(info["source"], "env_file")


if __name__ == "__main__":
    unittest.main()
