import os
import tempfile
import unittest

from bot import config
from bot.store.db import get_conn, init_db
from bot.store import repo
from bot.tasks import collectors


class CollectorsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "bot.db")
        init_db()
        repo.bind_guild("kook-guild", "albion-guild", "Top Squad", "admin")
        self.binding = repo.get_guild_binding("kook-guild")

    def tearDown(self):
        config.DB_PATH = self.old_db
        self.tmp.cleanup()

    async def test_repeated_battle_id_is_stored_once(self):
        gi = FakeCollectorGameInfo(
            battle_rows=[{"id": "battle-1"}, {"id": "battle-1"}],
            details={"battle-1": _battle_detail("battle-1")},
        )

        stats = await collectors.collect_recent_battles_once(gi, self.binding, limit=20)

        self.assertEqual(stats["stored"], 1)
        conn = get_conn()
        try:
            battle_count = conn.execute("SELECT COUNT(*) AS n FROM battle_snapshot").fetchone()["n"]
            participant_count = conn.execute(
                "SELECT COUNT(*) AS n FROM battle_participant WHERE battle_id='battle-1'"
            ).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(battle_count, 1)
        self.assertEqual(participant_count, 2)

    async def test_single_battle_detail_failure_does_not_stop_round(self):
        gi = FakeCollectorGameInfo(
            battle_rows=[{"id": "bad"}, {"id": "battle-2"}],
            details={"battle-2": _battle_detail("battle-2")},
            failing_ids={"bad"},
        )

        stats = await collectors.collect_recent_battles_once(gi, self.binding, limit=20)

        self.assertEqual(stats["stored"], 1)
        self.assertEqual(stats["errors"], 1)
        rows = repo.recent_collector_runs()
        self.assertEqual(rows[0]["status"], "partial")

    async def test_binding_without_battle_report_channel_still_collects_attendance(self):
        self.assertIsNone(self.binding.get("battle_report_channel_id"))
        gi = FakeCollectorGameInfo(
            battle_rows=[{"id": "battle-1"}],
            details={"battle-1": _battle_detail("battle-1")},
        )

        await collectors.collect_recent_battles_once(gi, self.binding, limit=20)

        conn = get_conn()
        try:
            battle_count = conn.execute("SELECT COUNT(*) AS n FROM battle_snapshot").fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(battle_count, 1)

        await collectors.collect_guild_members_once(gi, self.binding)
        snapshot = repo.recent_attendance_snapshot(
            "kook-guild",
            limit=20,
            min_guild_players=2,
        )
        self.assertEqual(snapshot["counted_battle_count"], 1)

    async def test_high_fame_collector_filters_bound_guild_events(self):
        gi = FakeCollectorGameInfo(
            events=[
                _event("keep-kill", killer_guild="albion-guild", fame=2_000_000),
                _event("keep-death", victim_guild="albion-guild", fame=1_500_000),
                _event("too-small", killer_guild="albion-guild", fame=999_999),
                _event("other-guild", killer_guild="other", victim_guild="elsewhere", fame=3_000_000),
            ]
        )

        stats = await collectors.collect_high_fame_events_once(
            gi,
            self.binding,
            fame_threshold=1_000_000,
        )

        self.assertEqual(stats["candidates"], 4)
        self.assertEqual(stats["stored"], 2)
        rows = repo.list_high_fame_events()
        self.assertEqual({row["event_id"] for row in rows}, {"keep-death", "keep-kill"})
        self.assertEqual(
            {row["event_id"]: row["fame"] for row in rows},
            {"keep-death": 1_500_000, "keep-kill": 2_000_000},
        )
        self.assertEqual(repo.recent_collector_runs()[0]["name"], "high_fame_events")

    async def test_leaderboard_collector_stores_dashboard_snapshots(self):
        gi = FakeCollectorGameInfo(
            leaderboards={
                "PvP": [{"Name": "PvP One", "Fame": 100}],
                "PvE": [{"Name": "PvE One", "Fame": 200}],
                "player_fame": [{"Name": "Fame One", "Fame": 300}],
                "guild_fame": [{"Name": "Guild One", "Fame": 400}],
            }
        )

        stats = await collectors.collect_fame_leaderboards_once(gi, limit=20)

        self.assertEqual(stats["snapshots"], 4)
        rows = repo.list_leaderboard_snapshots(limit=10)
        self.assertEqual({row["kind"] for row in rows}, {
            "player_pvp_week",
            "player_pve_week",
            "player_fame_week",
            "guild_fame_week",
        })
        self.assertEqual(rows[0]["kook_guild_id"], "global")
        self.assertIn("items", rows[0])

    async def test_gold_price_collector_stores_snapshot(self):
        market = FakeMarket(gold_rows=[{"timestamp": "2026-06-24T10:00:00Z", "price": 12345}])

        stats = await collectors.collect_gold_price_once(market, count=24)

        self.assertEqual(stats["rows"], 1)
        rows = repo.list_gold_price_snapshots()
        self.assertEqual(rows[0]["items"][0]["price"], 12345)
        self.assertEqual(repo.recent_collector_runs()[0]["name"], "gold_price")


class FakeCollectorGameInfo:
    def __init__(
        self,
        battle_rows=None,
        details=None,
        failing_ids=None,
        events=None,
        leaderboards=None,
    ):
        self.battle_rows = battle_rows or []
        self.details = details or {}
        self.failing_ids = set(failing_ids or [])
        self.event_rows = events or []
        self.leaderboards = leaderboards or {}

    async def guild_members(self, guild_id: str):
        return [
            {"Id": "a", "Name": "Alice"},
            {"Id": "b", "Name": "Bob"},
        ]

    async def battles(self, guild_id: str, limit: int):
        return self.battle_rows

    async def battle(self, battle_id: str):
        if battle_id in self.failing_ids:
            raise RuntimeError("boom")
        return self.details[battle_id]

    async def events(self, limit: int = 51, offset: int = 0):
        return self.event_rows[offset : offset + limit]

    async def player_statistics(self, type_: str = "PvE", range_: str = "week", limit: int = 11):
        return self.leaderboards.get(type_, [])[:limit]

    async def player_fame(self, range_: str = "week", limit: int = 11):
        return self.leaderboards.get("player_fame", [])[:limit]

    async def guild_fame(self, range_: str = "week", limit: int = 11):
        return self.leaderboards.get("guild_fame", [])[:limit]


class FakeMarket:
    def __init__(self, gold_rows=None):
        self.gold_rows = gold_rows or []

    async def gold(self, count: int = 24):
        return self.gold_rows[:count]


def _battle_detail(battle_id: str) -> dict:
    return {
        "id": battle_id,
        "startTime": "2026-06-24T10:00:00",
        "players": [
            {"id": "a", "name": "Alice", "guildId": "albion-guild", "kills": 1},
            {"id": "b", "name": "Bob", "guildId": "albion-guild", "deaths": 1},
        ],
    }


def _event(event_id: str, *, killer_guild="", victim_guild="", fame=0) -> dict:
    return {
        "EventId": event_id,
        "TimeStamp": f"2026-06-24T10:00:0{len(event_id) % 10}Z",
        "TotalVictimKillFame": fame,
        "Killer": {
            "Name": f"Killer {event_id}",
            "GuildId": killer_guild,
            "GuildName": killer_guild,
        },
        "Victim": {
            "Name": f"Victim {event_id}",
            "GuildId": victim_guild,
            "GuildName": victim_guild,
        },
    }


if __name__ == "__main__":
    unittest.main()
