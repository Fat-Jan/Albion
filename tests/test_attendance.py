import os
import tempfile
import unittest

from bot.albion.attendance import build_attendance_snapshot
from bot import config
from bot.commands import query
from bot.store.db import init_db
from bot.store import repo


class AttendanceSnapshotTest(unittest.TestCase):
    def test_counts_members_filters_threshold_and_keeps_absent_members(self):
        snapshot = build_attendance_snapshot(
            guild_id="guild-a",
            members=[
                {"Id": "a", "Name": "Alice"},
                {"Id": "b", "Name": "Bob"},
                {"Id": "c", "Name": "Cathy"},
            ],
            battle_details=[
                {
                    "id": "battle-1",
                    "startTime": "2026-06-24T10:00:00",
                    "players": {
                        "a": {"id": "a", "name": "Alice", "guildId": "guild-a", "kills": 2, "deaths": 0, "killFame": 1200},
                        "b": {"id": "b", "name": "Bob", "guildId": "guild-a", "kills": 0, "deaths": 1, "killFame": 0},
                        "x": {"id": "x", "name": "Enemy", "guildId": "guild-x", "kills": 1},
                    },
                },
                {
                    "id": "battle-2",
                    "startTime": "2026-06-24T11:00:00",
                    "players": [
                        {"Id": "a", "Name": "Alice", "GuildId": "guild-a", "Kills": 1, "Deaths": 0, "KillFame": 500}
                    ],
                },
            ],
            min_guild_players=2,
        )

        by_name = {row["name"]: row for row in snapshot["members"]}
        self.assertEqual(snapshot["battle_count"], 2)
        self.assertEqual(snapshot["counted_battle_count"], 1)
        self.assertEqual(snapshot["skipped_battles"][0]["battle_id"], "battle-2")
        self.assertEqual(by_name["Alice"]["participated_battles"], 1)
        self.assertEqual(by_name["Alice"]["participation_rate"], 100)
        self.assertEqual(by_name["Alice"]["kills"], 2)
        self.assertEqual(by_name["Bob"]["deaths"], 1)
        self.assertEqual(by_name["Cathy"]["participated_battles"], 0)
        self.assertEqual(by_name["Cathy"]["participation_rate"], 0)

    def test_members_with_same_participation_sort_by_newer_battle_first(self):
        snapshot = build_attendance_snapshot(
            guild_id="guild-a",
            members=[
                {"Id": "a", "Name": "Alice"},
                {"Id": "b", "Name": "Bob"},
            ],
            battle_details=[
                {
                    "id": "battle-old",
                    "startTime": "2026-06-24T10:00:00Z",
                    "players": [
                        {"id": "a", "name": "Alice", "guildId": "guild-a"},
                    ],
                },
                {
                    "id": "battle-new",
                    "startTime": "2026-06-24T12:00:00Z",
                    "players": [
                        {"id": "b", "name": "Bob", "guildId": "guild-a"},
                    ],
                },
            ],
            min_guild_players=1,
        )

        self.assertEqual([row["name"] for row in snapshot["members"]], ["Bob", "Alice"])


class AttendanceCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "bot.db")
        init_db()

    def tearDown(self):
        config.DB_PATH = self.old_db
        self.tmp.cleanup()

    async def test_attendance_defaults_to_twenty_battles(self):
        repo.bind_guild("kook-guild", "albion-guild", "Top Squad", "admin")
        msg = FakeMessage("kook-guild")
        gi = FakeAttendanceGameInfo()

        await query.reply_attendance(msg, gi, ())

        self.assertEqual(gi.battles_limits, [20])
        self.assertEqual(gi.battle_ids, ["battle-1"])
        self.assertIn("战斗参与快照", card_text(msg.replies[0]))

    async def test_attendance_caps_requested_battles_at_fifty(self):
        repo.bind_guild("kook-guild", "albion-guild", "Top Squad", "admin")
        msg = FakeMessage("kook-guild")
        gi = FakeAttendanceGameInfo()

        await query.reply_attendance(msg, gi, ("60",))

        self.assertEqual(gi.battles_limits, [50])

    async def test_attendance_uses_cache_when_enough_battles_exist(self):
        repo.bind_guild("kook-guild", "albion-guild", "Top Squad", "admin")
        repo.save_guild_member_snapshot(
            "kook-guild",
            "albion-guild",
            [{"Id": "a", "Name": "Alice"}],
            captured_at="2026-06-24T00:00:00Z",
        )
        for idx in range(5):
            repo.store_battle_detail(
                "kook-guild",
                "albion-guild",
                {
                    "id": f"battle-{idx}",
                    "startTime": f"2026-06-24T10:0{idx}:00",
                    "players": [
                        {"id": "a", "name": "Alice", "guildId": "albion-guild"},
                        {"id": f"x-{idx}", "name": f"Enemy {idx}", "guildId": "enemy"},
                    ],
                },
            )
        msg = FakeMessage("kook-guild")
        gi = FakeAttendanceGameInfo()

        await query.reply_attendance(msg, gi, ("5",))

        self.assertEqual(gi.battles_limits, [])
        self.assertIn("战斗参与快照", card_text(msg.replies[0]))

    async def test_attendance_fetches_live_when_cached_battles_lack_members(self):
        repo.bind_guild("kook-guild", "albion-guild", "Top Squad", "admin")
        for idx in range(5):
            repo.upsert_battle_snapshot(
                {
                    "battle_id": f"battle-{idx}",
                    "kook_guild_id": "kook-guild",
                    "albion_guild_id": "albion-guild",
                    "start_time": f"2026-06-24T10:0{idx}:00",
                    "guild_players": 20,
                    "total_players": 40,
                }
            )
        msg = FakeMessage("kook-guild")
        gi = FakeAttendanceGameInfo()

        await query.reply_attendance(msg, gi, ("5",))

        self.assertEqual(gi.battles_limits, [5])
        text = card_text(msg.replies[0])
        self.assertIn("Alice", text)
        self.assertIn("Bob", text)

    async def test_attendance_fetches_live_when_cached_battles_lack_participants(self):
        repo.bind_guild("kook-guild", "albion-guild", "Top Squad", "admin")
        repo.save_guild_member_snapshot(
            "kook-guild",
            "albion-guild",
            [
                {"Id": "a", "Name": "Alice"},
                {"Id": "b", "Name": "Bob"},
            ],
            captured_at="2026-06-24T00:00:00Z",
        )
        for idx in range(5):
            repo.upsert_battle_snapshot(
                {
                    "battle_id": f"battle-{idx}",
                    "kook_guild_id": "kook-guild",
                    "albion_guild_id": "albion-guild",
                    "start_time": f"2026-06-24T10:0{idx}:00",
                    "guild_players": 20,
                    "total_players": 40,
                }
            )
        msg = FakeMessage("kook-guild")
        gi = FakeAttendanceGameInfo()

        await query.reply_attendance(msg, gi, ("5",))

        self.assertEqual(gi.battles_limits, [5])
        text = card_text(msg.replies[0])
        self.assertIn("Alice", text)
        self.assertIn("Bob", text)

    async def test_attendance_live_fetch_populates_shared_cache(self):
        repo.bind_guild("kook-guild", "albion-guild", "Top Squad", "admin")
        msg = FakeMessage("kook-guild")
        gi = FakeAttendanceGameInfo()

        await query.reply_attendance(msg, gi, ("5",))

        snapshot = repo.recent_attendance_snapshot(
            "kook-guild",
            limit=5,
            min_guild_players=1,
        )
        by_name = {row["name"]: row for row in snapshot["members"]}
        self.assertEqual(snapshot["member_snapshot_count"], 2)
        self.assertEqual(snapshot["counted_battle_count"], 1)
        self.assertEqual(by_name["Alice"]["participated_battles"], 1)
        self.assertEqual(by_name["Bob"]["participated_battles"], 1)

    async def test_attendance_requires_bound_guild(self):
        msg = FakeMessage("missing-guild")
        gi = FakeAttendanceGameInfo()

        await query.reply_attendance(msg, gi, ())

        self.assertEqual(msg.replies, ["本服还没绑定公会，请管理员先 /绑定公会。"])
        self.assertEqual(gi.battles_limits, [])


class FakeCtx:
    def __init__(self, guild_id: str):
        self.guild = type("Guild", (), {"id": guild_id})()


class FakeMessage:
    def __init__(self, guild_id: str):
        self.ctx = FakeCtx(guild_id)
        self.replies = []

    async def reply(self, value):
        self.replies.append(value)


class FakeAttendanceGameInfo:
    def __init__(self):
        self.battles_limits = []
        self.battle_ids = []

    async def guild_members(self, guild_id: str):
        return [
            {"Id": "a", "Name": "Alice"},
            {"Id": "b", "Name": "Bob"},
        ]

    async def battles(self, guild_id: str, limit: int):
        self.battles_limits.append(limit)
        return [{"id": "battle-1"}]

    async def battle(self, battle_id: str):
        self.battle_ids.append(battle_id)
        return {
            "id": battle_id,
            "startTime": "2026-06-24T10:00:00",
            "players": [
                {"id": "a", "name": "Alice", "guildId": "albion-guild"},
                {"id": "b", "name": "Bob", "guildId": "albion-guild"},
            ],
        }


def card_text(card_message) -> str:
    texts = []
    for card in list(card_message):
        for module in card.get("modules", []):
            text = module.get("text")
            if isinstance(text, dict):
                texts.append(text.get("content", ""))
            elif isinstance(text, str):
                texts.append(text)
    return "\n".join(texts)


if __name__ == "__main__":
    unittest.main()
