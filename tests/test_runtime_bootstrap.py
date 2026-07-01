import os
import tempfile
import unittest

from bot import config
from bot.store import repo
from bot.store.bootstrap import seed_runtime_guild_config
from bot.store.db import init_db


class RuntimeBootstrapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "bot.db")
        init_db()

    def tearDown(self):
        config.DB_PATH = self.old_db
        self.tmp.cleanup()

    def test_seed_eu_runtime_guild_config(self):
        cfg = seed_runtime_guild_config("eu")

        self.assertIsNotNone(cfg)
        row = repo.get_guild_binding("4676167053713576", "eu")
        self.assertEqual(row["albion_guild_name"], "Top Squad")
        self.assertEqual(row["albion_guild_id"], "7tmt12sOTkGgcqZL3jSy7Q")
        self.assertEqual(row["kill_broadcast_channel_id"], "8415323442916410")
        self.assertEqual(row["death_broadcast_channel_id"], "3162690807846766")
        self.assertEqual(row["battle_report_channel_id"], "7532177792027984")
        self.assertEqual(row["battle_report_min_guild_players"], 20)
        self.assertEqual(row["member_change_channel_id"], "3626370873673494")
        self.assertEqual(row["kill_fame_threshold"], 100000)

    def test_seed_asia_runtime_guild_config(self):
        cfg = seed_runtime_guild_config("asia")

        self.assertIsNotNone(cfg)
        row = repo.get_guild_binding("4676167053713576", "asia")
        self.assertEqual(row["albion_guild_name"], "Mika")
        self.assertEqual(row["albion_guild_id"], "KVO3_vrITECLAIRl1juHSg")
        self.assertEqual(row["member_role_id"], "47139243")
        self.assertEqual(row["kill_broadcast_channel_id"], "4326560318750543")
        self.assertEqual(row["death_broadcast_channel_id"], "5193310241387334")
        self.assertEqual(row["battle_report_channel_id"], "3891092612097998")
        self.assertEqual(row["member_change_channel_id"], "1203064556541945")
        self.assertEqual(row["kill_fame_threshold"], 400000)

    def test_seed_unknown_region_does_not_write_binding(self):
        cfg = seed_runtime_guild_config("unknown")

        self.assertIsNone(cfg)
        self.assertEqual(repo.all_guild_bindings(), [])

    def test_region_seed_keeps_same_kook_guild_distinct_per_region(self):
        seed_runtime_guild_config("asia")
        seed_runtime_guild_config("eu")

        eu = repo.get_guild_binding("4676167053713576", "eu")
        asia = repo.get_guild_binding("4676167053713576", "asia")
        self.assertEqual(eu["albion_guild_name"], "Top Squad")
        self.assertEqual(eu["kill_broadcast_channel_id"], "8415323442916410")
        self.assertEqual(asia["albion_guild_name"], "Mika")
        self.assertEqual(asia["kill_broadcast_channel_id"], "4326560318750543")

    def test_seed_preserves_existing_same_region_manual_setting(self):
        seed_runtime_guild_config("eu")
        repo.set_setting("4676167053713576", "kill_broadcast_channel_id", "manual-channel")

        seed_runtime_guild_config("eu")

        row = repo.get_guild_binding("4676167053713576", "eu")
        self.assertEqual(row["kill_broadcast_channel_id"], "manual-channel")

    def test_seed_fills_missing_same_region_setting(self):
        repo.bind_guild(
            "4676167053713576",
            "7tmt12sOTkGgcqZL3jSy7Q",
            "Top Squad",
            "admin",
        )

        seed_runtime_guild_config("eu")

        row = repo.get_guild_binding("4676167053713576", "eu")
        self.assertEqual(row["death_broadcast_channel_id"], "3162690807846766")
