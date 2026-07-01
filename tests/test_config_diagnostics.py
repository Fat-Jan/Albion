import hashlib
import importlib
import os
import unittest
from unittest.mock import patch

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

    def test_region_configs_include_eu_and_asia_defaults(self):
        self.assertEqual(set(config.REGION_CONFIGS), {"eu", "asia"})
        self.assertEqual(config.REGION_CONFIGS["eu"].region_code, "eu")
        self.assertEqual(config.REGION_CONFIGS["asia"].region_code, "asia")
        self.assertEqual(
            config.REGION_CONFIGS["eu"].gameinfo_base,
            "https://gameinfo-ams.albiononline.com/api/gameinfo",
        )
        self.assertEqual(
            config.REGION_CONFIGS["asia"].gameinfo_base,
            "https://gameinfo-sgp.albiononline.com/api/gameinfo",
        )
        self.assertEqual(config.REGION_CONFIGS["asia"].killboard_server, "live_sgp")

    def test_legacy_single_value_env_is_eu_fallback_only(self):
        keys = (
            "KOOK_TOKEN_EU",
            "GAMEINFO_BASE_EU",
            "AODP_BASE_EU",
            "ALBIONBB_BASE_EU",
            "ALBIONBB_WEB_BASE_EU",
            "KILLBOARD_SERVER_EU",
        )
        old_values = {key: os.environ.pop(key, None) for key in keys}
        self.addCleanup(self._restore_env, old_values)
        env = {
            "KOOK_TOKEN": "1/MTIzNDU=/legacy",
            "GAMEINFO_BASE": "https://legacy-gameinfo.example/api",
            "AODP_BASE": "https://legacy-aodp.example",
            "ALBIONBB_BASE": "https://legacy-bb-api.example/eu",
            "ALBIONBB_WEB_BASE": "https://legacy-bb-web.example",
            "KILLBOARD_SERVER": "legacy_live",
        }
        with patch.dict(os.environ, env, clear=False):
            reloaded = importlib.reload(config)
            self.addCleanup(importlib.reload, config)

            self.assertEqual(reloaded.REGION_CONFIGS["eu"].kook_token, env["KOOK_TOKEN"])
            self.assertEqual(
                reloaded.REGION_CONFIGS["eu"].gameinfo_base, env["GAMEINFO_BASE"]
            )
            self.assertEqual(
                reloaded.REGION_CONFIGS["asia"].gameinfo_base,
                "https://gameinfo-sgp.albiononline.com/api/gameinfo",
            )

    @staticmethod
    def _restore_env(values: dict[str, str | None]) -> None:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
