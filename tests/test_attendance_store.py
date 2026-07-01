import os
import tempfile
import unittest

from bot import config
from bot.store.db import get_conn, init_db
from bot.store import repo


class AttendanceStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "bot.db")
        init_db()

    def tearDown(self):
        config.DB_PATH = self.old_db
        self.tmp.cleanup()

    def test_attendance_tables_exist_after_init(self):
        conn = get_conn()
        try:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()

        self.assertIn("guild_member_snapshot", tables)
        self.assertIn("battle_snapshot", tables)
        self.assertIn("battle_participant", tables)
        self.assertIn("collector_cursor", tables)

    def test_dashboard_indexes_exist_after_init(self):
        conn = get_conn()
        try:
            indexes = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                ).fetchall()
            }
        finally:
            conn.close()

        self.assertIn("idx_guild_member_snapshot_latest", indexes)
        self.assertIn("idx_battle_snapshot_guild_time", indexes)
        self.assertIn("idx_battle_participant_battle", indexes)
        self.assertIn("idx_collector_cursor_last_run", indexes)
        self.assertIn("idx_high_fame_event_time", indexes)
        self.assertIn("idx_leaderboard_snapshot_kind_time", indexes)
        self.assertIn("idx_gold_price_snapshot_time", indexes)

    def test_recent_attendance_snapshot_rebuilds_from_cached_rows(self):
        repo.bind_guild("kook-guild", "albion-guild", "Top Squad", "admin")
        repo.save_guild_member_snapshot(
            "kook-guild",
            "albion-guild",
            [
                {"Id": "a", "Name": "Alice"},
                {"Id": "b", "Name": "Bob"},
                {"Id": "c", "Name": "Cathy"},
            ],
            captured_at="2026-06-24T00:00:00Z",
        )
        detail = {
            "id": "battle-1",
            "startTime": "2026-06-24T10:00:00",
            "players": [
                {"id": "a", "name": "Alice", "guildId": "albion-guild", "kills": 2, "killFame": 1000},
                {"id": "b", "name": "Bob", "guildId": "albion-guild", "deaths": 1},
                {"id": "x", "name": "Enemy", "guildId": "enemy"},
            ],
        }

        repo.store_battle_detail("kook-guild", "albion-guild", detail)
        repo.store_battle_detail("kook-guild", "albion-guild", detail)
        snapshot = repo.recent_attendance_snapshot(
            "kook-guild",
            limit=20,
            min_guild_players=2,
        )

        by_name = {row["name"]: row for row in snapshot["members"]}
        self.assertEqual(snapshot["counted_battle_count"], 1)
        self.assertEqual(by_name["Alice"]["participated_battles"], 1)
        self.assertEqual(by_name["Bob"]["deaths"], 1)
        self.assertEqual(by_name["Cathy"]["participated_battles"], 0)

        conn = get_conn()
        try:
            count = conn.execute("SELECT COUNT(*) AS n FROM battle_snapshot").fetchone()["n"]
            participants = conn.execute(
                "SELECT COUNT(*) AS n FROM battle_participant WHERE battle_id='battle-1'"
            ).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(count, 1)
        self.assertEqual(participants, 3)

    def test_same_battle_can_be_cached_for_multiple_kook_guilds(self):
        repo.bind_guild("kook-guild-a", "albion-guild", "Top Squad", "admin")
        repo.bind_guild("kook-guild-b", "albion-guild", "Top Squad", "admin")
        for kook_guild_id in ("kook-guild-a", "kook-guild-b"):
            repo.save_guild_member_snapshot(
                kook_guild_id,
                "albion-guild",
                [{"Id": "a", "Name": "Alice"}],
                captured_at="2026-06-24T00:00:00Z",
            )

        detail = {
            "id": "shared-battle",
            "startTime": "2026-06-24T10:00:00",
            "players": [
                {"id": "a", "name": "Alice", "guildId": "albion-guild"},
                {"id": "x", "name": "Enemy", "guildId": "enemy"},
            ],
        }
        repo.store_battle_detail("kook-guild-a", "albion-guild", detail)
        repo.store_battle_detail("kook-guild-b", "albion-guild", detail)

        first = repo.recent_attendance_snapshot(
            "kook-guild-a",
            limit=5,
            min_guild_players=1,
        )
        second = repo.recent_attendance_snapshot(
            "kook-guild-b",
            limit=5,
            min_guild_players=1,
        )

        self.assertEqual(first["battle_count"], 1)
        self.assertEqual(first["counted_battle_count"], 1)
        self.assertEqual(second["battle_count"], 1)
        self.assertEqual(second["counted_battle_count"], 1)

    def test_init_db_migrates_legacy_battle_snapshot_scope(self):
        os.remove(config.DB_PATH)
        conn = get_conn()
        try:
            conn.executescript(
                """
                CREATE TABLE battle_snapshot (
                  battle_id        TEXT PRIMARY KEY,
                  kook_guild_id    TEXT NOT NULL,
                  albion_guild_id  TEXT NOT NULL,
                  start_time       TEXT,
                  guild_players    INTEGER DEFAULT 0,
                  total_players    INTEGER DEFAULT 0,
                  total_kills      INTEGER DEFAULT 0,
                  total_fame       INTEGER DEFAULT 0,
                  captured_at      TEXT DEFAULT (datetime('now'))
                );
                """
            )
            conn.commit()
        finally:
            conn.close()
        init_db()

        repo.bind_guild("kook-guild-a", "albion-guild", "Top Squad", "admin")
        repo.bind_guild("kook-guild-b", "albion-guild", "Top Squad", "admin")
        for kook_guild_id in ("kook-guild-a", "kook-guild-b"):
            repo.save_guild_member_snapshot(
                kook_guild_id,
                "albion-guild",
                [{"Id": "a", "Name": "Alice"}],
                captured_at="2026-06-24T00:00:00Z",
            )

        detail = {
            "id": "legacy-shared-battle",
            "startTime": "2026-06-24T10:00:00",
            "players": [
                {"id": "a", "name": "Alice", "guildId": "albion-guild"},
            ],
        }
        repo.store_battle_detail("kook-guild-a", "albion-guild", detail)
        repo.store_battle_detail("kook-guild-b", "albion-guild", detail)

        first = repo.recent_attendance_snapshot(
            "kook-guild-a",
            limit=5,
            min_guild_players=1,
        )
        second = repo.recent_attendance_snapshot(
            "kook-guild-b",
            limit=5,
            min_guild_players=1,
        )

        self.assertEqual(first["counted_battle_count"], 1)
        self.assertEqual(second["counted_battle_count"], 1)
        conn = get_conn()
        try:
            indexes = {
                row["name"]
                for row in conn.execute("PRAGMA index_list(battle_snapshot)")
            }
        finally:
            conn.close()
        self.assertIn("idx_battle_snapshot_guild_time", indexes)

    def test_collector_cursor_is_idempotent(self):
        repo.mark_collector_run("attendance_battles", "kook-guild", status="error", error="boom")
        repo.mark_collector_run("attendance_battles", "kook-guild", status="ok")

        rows = repo.recent_collector_runs()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "attendance_battles")
        self.assertEqual(rows[0]["status"], "ok")
        self.assertIsNone(rows[0]["error"])

    def test_same_high_fame_event_can_be_cached_for_multiple_kook_guilds(self):
        event = {
            "EventId": "shared-event",
            "TimeStamp": "2026-06-24T10:00:00Z",
            "TotalVictimKillFame": 2_000_000,
            "Killer": {"Name": "Alice", "GuildId": "albion-guild"},
            "Victim": {"Name": "Bob", "GuildId": "other"},
        }

        repo.save_high_fame_events(
            "kook-guild-a",
            "albion-guild",
            [event],
        )
        repo.save_high_fame_events(
            "kook-guild-b",
            "albion-guild",
            [event],
        )

        rows = repo.list_high_fame_events(limit=10)

        self.assertEqual(
            {(row["kook_guild_id"], row["event_id"]) for row in rows},
            {("kook-guild-a", "shared-event"), ("kook-guild-b", "shared-event")},
        )

    def test_init_db_migrates_legacy_high_fame_event_scope(self):
        os.remove(config.DB_PATH)
        conn = get_conn()
        try:
            conn.executescript(
                """
                CREATE TABLE high_fame_event (
                  event_id      TEXT PRIMARY KEY,
                  kook_guild_id TEXT,
                  event_time    TEXT,
                  payload_json  TEXT
                );
                """
            )
            conn.commit()
        finally:
            conn.close()
        init_db()

        event = {
            "EventId": "legacy-shared-event",
            "TimeStamp": "2026-06-24T10:00:00Z",
            "TotalVictimKillFame": 2_000_000,
            "Killer": {"Name": "Alice", "GuildId": "albion-guild"},
            "Victim": {"Name": "Bob", "GuildId": "other"},
        }
        repo.save_high_fame_events("kook-guild-a", "albion-guild", [event])
        repo.save_high_fame_events("kook-guild-b", "albion-guild", [event])

        rows = repo.list_high_fame_events(limit=10)

        self.assertEqual(
            {(row["kook_guild_id"], row["event_id"]) for row in rows},
            {
                ("kook-guild-a", "legacy-shared-event"),
                ("kook-guild-b", "legacy-shared-event"),
            },
        )
        conn = get_conn()
        try:
            indexes = {
                row["name"]
                for row in conn.execute("PRAGMA index_list(high_fame_event)")
            }
        finally:
            conn.close()
        self.assertIn("idx_high_fame_event_time", indexes)

    def test_dashboard_snapshot_pruning_keeps_latest_rows(self):
        for idx in range(4):
            repo.save_leaderboard_snapshot(
                "player_pvp_week",
                [{"Name": f"pvp-{idx}"}],
                captured_at=f"2026-06-24T10:0{idx}:00Z",
            )
            repo.save_leaderboard_snapshot(
                "player_pve_week",
                [{"Name": f"pve-{idx}"}],
                captured_at=f"2026-06-24T11:0{idx}:00Z",
            )
        repo.prune_leaderboard_snapshots(keep_per_kind=2)

        for idx in range(4):
            repo.save_gold_price_snapshot(
                [{"price": 12000 + idx}],
                captured_at=f"2026-06-24T12:0{idx}:00Z",
            )
        repo.prune_gold_price_snapshots(keep=2)

        conn = get_conn()
        try:
            counts = {
                row["kind"]: row["n"]
                for row in conn.execute(
                    """
                    SELECT kind, COUNT(*) AS n
                    FROM fame_leaderboard_snapshot
                    GROUP BY kind
                    """
                ).fetchall()
            }
            prices = [
                row["captured_at"]
                for row in conn.execute(
                    "SELECT captured_at FROM gold_price_snapshot ORDER BY captured_at"
                ).fetchall()
            ]
        finally:
            conn.close()

        self.assertEqual(counts, {"player_pve_week": 2, "player_pvp_week": 2})
        self.assertEqual(
            prices,
            ["2026-06-24T12:02:00Z", "2026-06-24T12:03:00Z"],
        )


if __name__ == "__main__":
    unittest.main()
