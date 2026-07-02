import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from bot import config
from bot.store import repo
from bot.store.db import get_conn, init_db


class RegionIsolationStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "bot.db")
        init_db()

    def tearDown(self):
        config.DB_PATH = self.old_db
        self.tmp.cleanup()

    def test_same_kook_guild_can_have_distinct_region_bindings(self):
        repo.bind_guild("shared-guild", "eu", "eu-albion", "Top Squad", "admin")
        repo.bind_guild("shared-guild", "asia", "asia-albion", "Mika", "admin")

        eu = repo.get_guild_binding("shared-guild", "eu")
        asia = repo.get_guild_binding("shared-guild", "asia")

        self.assertEqual(eu["albion_guild_name"], "Top Squad")
        self.assertEqual(asia["albion_guild_name"], "Mika")
        self.assertEqual(
            {row["region"] for row in repo.all_guild_bindings()},
            {"eu", "asia"},
        )
        self.assertEqual(
            [row["albion_guild_name"] for row in repo.all_guild_bindings(region="eu")],
            ["Top Squad"],
        )

    def test_player_regear_and_battle_state_are_region_scoped(self):
        repo.bind_guild("shared-guild", "eu", "eu-albion", "Top Squad", "admin")
        repo.bind_guild("shared-guild", "asia", "asia-albion", "Mika", "admin")
        repo.set_player_binding("user-1", "shared-guild", "eu", "eu-player", "EuName")
        repo.set_player_binding("user-1", "shared-guild", "asia", "asia-player", "AsiaName")

        self.assertEqual(
            repo.get_player_binding("user-1", "shared-guild", "eu")["albion_player_id"],
            "eu-player",
        )
        self.assertEqual(
            repo.get_player_binding("user-1", "shared-guild", "asia")["albion_player_id"],
            "asia-player",
        )

        eu_regear = repo.create_regear("shared-guild", "eu", "user-1", "eu-player", "e1", 100)
        asia_regear = repo.create_regear(
            "shared-guild", "asia", "user-1", "asia-player", "e2", 200
        )

        self.assertEqual([row["id"] for row in repo.list_regear("shared-guild", "eu")], [eu_regear])
        self.assertEqual(
            [row["id"] for row in repo.list_regear("shared-guild", "asia")],
            [asia_regear],
        )

        self.assertFalse(repo.has_seen_battle_report("shared-guild", "eu", "battle-1"))
        repo.mark_battle_report_seen("shared-guild", "eu", "battle-1")
        self.assertTrue(repo.has_seen_battle_report("shared-guild", "eu", "battle-1"))
        self.assertFalse(repo.has_seen_battle_report("shared-guild", "asia", "battle-1"))

    def test_legacy_schema_is_backfilled_with_default_region_without_losing_rows(self):
        os.remove(config.DB_PATH)
        conn = get_conn()
        try:
            conn.executescript(
                """
                CREATE TABLE guild_binding (
                  kook_guild_id TEXT PRIMARY KEY,
                  albion_guild_id TEXT NOT NULL,
                  albion_guild_name TEXT NOT NULL,
                  created_by TEXT,
                  created_at TEXT DEFAULT (datetime('now'))
                );
                INSERT INTO guild_binding
                  (kook_guild_id, albion_guild_id, albion_guild_name, created_by)
                VALUES ('guild-legacy', 'albion-legacy', 'Legacy Guild', 'admin');

                CREATE TABLE player_binding (
                  kook_user_id TEXT NOT NULL,
                  kook_guild_id TEXT NOT NULL,
                  albion_player_id TEXT NOT NULL,
                  albion_player_name TEXT NOT NULL,
                  status TEXT DEFAULT 'verified',
                  bound_at TEXT DEFAULT (datetime('now')),
                  PRIMARY KEY (kook_user_id, kook_guild_id)
                );
                INSERT INTO player_binding
                  (kook_user_id, kook_guild_id, albion_player_id, albion_player_name)
                VALUES ('user-legacy', 'guild-legacy', 'player-legacy', 'LegacyPlayer');
                """
            )
            conn.commit()
        finally:
            conn.close()

        init_db()

        row = repo.get_guild_binding("guild-legacy", "eu")
        player = repo.get_player_binding("user-legacy", "guild-legacy", "eu")

        self.assertEqual(row["region"], "eu")
        self.assertEqual(row["albion_guild_name"], "Legacy Guild")
        self.assertEqual(player["region"], "eu")
        self.assertEqual(player["albion_player_name"], "LegacyPlayer")
        conn = get_conn()
        try:
            counts = {
                table: conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
                for table in ("guild_binding", "player_binding")
            }
        finally:
            conn.close()
        self.assertEqual(counts, {"guild_binding": 1, "player_binding": 1})


class RegionIsolationMainTest(unittest.TestCase):
    def test_build_bots_creates_one_bot_per_configured_region(self):
        from bot import main

        regions = {
            "eu": config.AlbionRegionConfig(
                region_code="eu",
                kook_token="1/NDkwNTA=/eu",
                gameinfo_base="https://gameinfo-eu.example",
                aodp_base="https://aodp-eu.example",
                albionbb_base="https://bb-eu.example",
                albionbb_web_base="https://bb-web-eu.example",
                killboard_server="live_ams",
                display_tz="Asia/Shanghai",
                display_tz_label="北京时间",
                display_tz_short_label="北京",
            ),
            "asia": config.AlbionRegionConfig(
                region_code="asia",
                kook_token="1/NDkwMjU=/asia",
                gameinfo_base="https://gameinfo-asia.example",
                aodp_base="https://aodp-asia.example",
                albionbb_base="https://bb-asia.example",
                albionbb_web_base="https://bb-web-asia.example",
                killboard_server="live_sgp",
                display_tz="Asia/Shanghai",
                display_tz_label="北京时间",
                display_tz_short_label="北京",
            ),
        }

        with (
            patch.object(main.config, "REGION_CONFIGS", regions),
            patch.object(main, "init_db"),
            patch.object(main, "seed_runtime_guild_config"),
            patch.object(main, "Bot", side_effect=lambda token: Mock(token=token)),
            patch.object(main, "AlbionClient"),
            patch.object(main, "GameInfo"),
            patch.object(main, "Market"),
            patch.object(main.admin, "register"),
            patch.object(main.register, "register"),
            patch.object(main.query, "register"),
            patch.object(main.regear, "register"),
            patch.object(main.ai, "register"),
            patch.object(main.auto, "register"),
        ):
            bots = main.build_bots()

        self.assertEqual([bot._region for bot in bots], ["eu", "asia"])
        self.assertEqual([bot.token for bot in bots], ["1/NDkwNTA=/eu", "1/NDkwMjU=/asia"])


if __name__ == "__main__":
    unittest.main()
