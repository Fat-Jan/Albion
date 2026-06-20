import os
import tempfile
import unittest
from datetime import datetime

from bot.albion.battle_report import build_battle_report
from bot.cards.battle_report_cards import battle_report_card
from bot import config
from bot.store.db import init_db
from bot.store import repo
from bot.tasks import auto


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


def section_texts(card_message) -> list[str]:
    texts = []
    for card in list(card_message):
        for module in card.get("modules", []):
            if module.get("type") != "section":
                continue
            text = module.get("text")
            if isinstance(text, dict):
                texts.append(text.get("content", ""))
            elif isinstance(text, str):
                texts.append(text)
    return texts


class BattleReportTest(unittest.TestCase):
    def test_report_counts_high_participation_guilds_and_alliances(self):
        report = build_battle_report(
            _battle_detail(),
            _battle_events(),
            guild_name="Mika",
        )

        self.assertEqual(report["guild_players"], 3)
        self.assertEqual(
            [(r["name"], r["players"]) for r in report["top_guilds"]],
            [("Mika", 3), ("CCTV", 2), ("Nazareno", 1)],
        )
        self.assertEqual(
            [(r["name"], r["players"]) for r in report["top_alliances"]],
            [("5I7", 3), ("HDD", 2), ("MONKY", 1)],
        )

    def test_report_highlights_four_guild_player_leaders(self):
        report = build_battle_report(
            _battle_detail(),
            _battle_events(),
            guild_name="Mika",
        )

        highlights = report["player_highlights"]
        self.assertEqual(highlights["most_kills"]["name"], "Alice")
        self.assertEqual(highlights["top_kill_fame"]["name"], "Bob")
        self.assertEqual(highlights["most_deaths"]["name"], "Bob")
        self.assertEqual(highlights["top_death_fame"]["name"], "Cathy")
        self.assertEqual(highlights["top_death_fame"]["death_fame"], 900_000)

    def test_report_adds_guild_rank_share_delta_and_main_enemies(self):
        report = build_battle_report(
            _battle_detail(),
            _battle_events(),
            guild_name="Mika",
        )

        self.assertEqual(report["guild_rank"], 1)
        self.assertEqual(report["guild_count"], 3)
        self.assertEqual(report["guild_participation_percent"], 50)
        self.assertEqual(report["guild_kill_death_delta"], 1)
        self.assertEqual(
            [(r["name"], r["players"]) for r in report["enemy_guilds"]],
            [("CCTV", 2), ("Nazareno", 1)],
        )

    def test_report_uses_configured_albionbb_web_base(self):
        old_base = config.ALBIONBB_WEB_BASE
        try:
            config.ALBIONBB_WEB_BASE = "https://europe.albionbb.com"
            report = build_battle_report(
                _battle_detail(),
                _battle_events(),
                guild_name="Mika",
            )
        finally:
            config.ALBIONBB_WEB_BASE = old_base

        self.assertEqual(
            report["battle_url"], "https://europe.albionbb.com/battles/123"
        )

    def test_card_marks_participant_counts_and_player_leaders(self):
        report = build_battle_report(
            _battle_detail(),
            _battle_events(),
            guild_name="Mika",
        )

        text = card_text(battle_report_card(report))
        sections = section_texts(battle_report_card(report))

        self.assertIn("**战场概况**", text)
        self.assertIn("**本会表现**", text)
        self.assertIn("**公会战力榜**", text)
        self.assertIn("**联盟战力榜**", text)
        self.assertIn("**本会高光**", text)
        self.assertTrue(any("整场 6 人" in s and "总声望 `123.5万`" in s for s in sections))
        self.assertIn("Mika [5I7]　3人", text)
        self.assertIn("CCTV [HDD]　2人", text)
        self.assertIn("5I7　3人", text)
        self.assertIn("排名 `第 1/3`", text)
        self.assertIn("参战占比 `50%`", text)
        self.assertIn("击杀差 `+1`", text)
        self.assertIn("**主要对手**", text)
        self.assertIn("击杀最多：`Alice`　3 次", text)
        self.assertIn("击杀声望最高：`Bob`　`2.0万`", text)
        self.assertIn("阵亡最多：`Bob`　2 次", text)
        self.assertIn("阵亡声望最高：`Cathy`　`90.0万`", text)


class BattleReportAutoTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "bot.db")
        init_db()

    def tearDown(self):
        config.DB_PATH = self.old_db
        self.tmp.cleanup()

    def test_battle_report_window_uses_beijing_cross_midnight_range(self):
        self.assertFalse(auto._should_run_battle_report(datetime(2026, 6, 14, 6, 29)))
        self.assertTrue(auto._should_run_battle_report(datetime(2026, 6, 14, 6, 30)))
        self.assertTrue(auto._should_run_battle_report(datetime(2026, 6, 14, 15, 59)))
        self.assertTrue(auto._should_run_battle_report(datetime(2026, 6, 14, 20, 59)))
        self.assertFalse(auto._should_run_battle_report(datetime(2026, 6, 14, 21, 0)))

    def test_battle_report_window_uses_configured_timezone_and_hours(self):
        old_tz = config.DISPLAY_TZ
        old_start = config.BATTLE_REPORT_WINDOW_START
        old_end = config.BATTLE_REPORT_WINDOW_END
        try:
            config.DISPLAY_TZ = "UTC"
            config.BATTLE_REPORT_WINDOW_START = "10:00"
            config.BATTLE_REPORT_WINDOW_END = "11:00"

            self.assertFalse(auto._should_run_battle_report(datetime(2026, 6, 14, 9, 59)))
            self.assertTrue(auto._should_run_battle_report(datetime(2026, 6, 14, 10, 30)))
            self.assertFalse(auto._should_run_battle_report(datetime(2026, 6, 14, 11, 0)))
        finally:
            config.DISPLAY_TZ = old_tz
            config.BATTLE_REPORT_WINDOW_START = old_start
            config.BATTLE_REPORT_WINDOW_END = old_end

    def test_battle_report_interval_is_three_minutes(self):
        self.assertEqual(auto.BATTLE_REPORT_INTERVAL_MIN, 3)

    def test_seen_table_is_persistent_per_kook_guild_and_battle(self):
        repo.bind_guild("guild-a", "albion-a", "Mika", "admin")
        repo.bind_guild("guild-b", "albion-a", "Mika", "admin")

        self.assertFalse(repo.has_seen_battle_report("guild-a", "battle-1"))
        repo.mark_battle_report_seen("guild-a", "battle-1")

        self.assertTrue(repo.has_seen_battle_report("guild-a", "battle-1"))
        self.assertFalse(repo.has_seen_battle_report("guild-b", "battle-1"))

    async def test_battle_report_tick_sends_and_marks_seen_after_success(self):
        repo.bind_guild("guild", "albion-guild", "Mika", "admin")
        repo.set_setting("guild", "battle_report_channel_id", "battle-channel")
        repo.set_setting("guild", "battle_report_min_guild_players", 2)
        bot = FakeBot(channel_names={"battle-channel": "eu-🗺️战报推送"})
        gi = FakeBattleGameInfo(_battle_detail_with_guild_players(20), _battle_events())
        bb = FakeAlbionBB(
            [
                {
                    "albionId": "123",
                    "guilds": [{"name": "Mika", "killFame": 32000}],
                }
            ]
        )

        await auto._run_battle_report_tick(
            bot,
            gi,
            bb,
            now=datetime(2026, 6, 14, 6, 30),
        )

        self.assertEqual(gi.battles_calls, [{"guild_id": "albion-guild", "limit": 20}])
        self.assertEqual(bb.calls, [{"minPlayers": 20, "page": 1}])
        self.assertEqual(bot.client.channels["battle-channel"].send_count, 1)
        self.assertTrue(repo.has_seen_battle_report("guild", "123"))

    async def test_battle_report_tick_prefers_official_guild_battles_before_albionbb(self):
        repo.bind_guild("guild", "albion-guild", "Mika", "admin")
        repo.set_setting("guild", "battle_report_channel_id", "battle-channel")
        repo.set_setting("guild", "battle_report_min_guild_players", 2)
        bot = FakeBot()
        gi = FakeBattleGameInfo(
            _battle_detail_with_guild_players(20),
            _battle_events(),
            battle_rows=[
                {"id": "official-1"},
                {"id": "shared-1"},
            ],
        )
        bb = FakeAlbionBB(
            [
                {"albionId": "shared-1", "guilds": [{"name": "Mika"}]},
                {"albionId": "bb-only", "guilds": [{"name": "Mika"}]},
            ]
        )

        await auto._run_battle_report_tick(
            bot,
            gi,
            bb,
            now=datetime(2026, 6, 14, 6, 30),
        )

        self.assertEqual(gi.battle_ids, ["official-1", "shared-1", "bb-only"])
        self.assertEqual(bot.client.channels["battle-channel"].send_count, 3)
        self.assertTrue(repo.has_seen_battle_report("guild", "official-1"))

    async def test_battle_report_tick_skips_non_region_channel_without_marking_seen(self):
        repo.bind_guild("guild", "albion-guild", "Mika", "admin")
        repo.set_setting("guild", "battle_report_channel_id", "battle-channel")
        repo.set_setting("guild", "battle_report_min_guild_players", 2)
        bot = FakeBot(channel_names={"battle-channel": "🗺️战报推送"})
        gi = FakeBattleGameInfo(_battle_detail_with_guild_players(20), _battle_events())
        bb = FakeAlbionBB(
            [
                {
                    "albionId": "123",
                    "guilds": [{"name": "Mika", "killFame": 32000}],
                }
            ]
        )

        await auto._run_battle_report_tick(
            bot,
            gi,
            bb,
            now=datetime(2026, 6, 14, 6, 30),
        )

        self.assertEqual(bot.client.channels["battle-channel"].send_count, 0)
        self.assertFalse(repo.has_seen_battle_report("guild", "123"))

    async def test_battle_report_tick_includes_ai_summary_when_available(self):
        repo.bind_guild("guild", "albion-guild", "Mika", "admin")
        repo.set_setting("guild", "battle_report_channel_id", "battle-channel")
        repo.set_setting("guild", "battle_report_min_guild_players", 2)
        bot = FakeBot()
        gi = FakeBattleGameInfo(_battle_detail_with_guild_players(20), _battle_events())
        bb = FakeAlbionBB(
            [
                {
                    "albionId": "123",
                    "guilds": [{"name": "Mika", "killFame": 32000}],
                }
            ]
        )
        ai_service = FakeAIService("本会参战 3 人，击杀声望稳定，Bob 阵亡压力较高。")

        await auto._run_battle_report_tick(
            bot,
            gi,
            bb,
            now=datetime(2026, 6, 14, 6, 30),
            ai_service=ai_service,
        )

        message = bot.client.channels["battle-channel"].last_message
        text = card_text(message)
        self.assertEqual(ai_service.report_calls[0]["guild_name"], "Mika")
        self.assertIn("**AI 摘要**", text)
        self.assertIn("本会参战 3 人", text)

    async def test_battle_report_tick_enforces_at_least_twenty_guild_players(self):
        repo.bind_guild("guild", "albion-guild", "Mika", "admin")
        repo.set_setting("guild", "battle_report_channel_id", "battle-channel")
        repo.set_setting("guild", "battle_report_min_guild_players", 5)
        bot = FakeBot()
        gi = FakeBattleGameInfo(_battle_detail_with_guild_players(6), _battle_events())
        bb = FakeAlbionBB(
            [
                {
                    "albionId": "123",
                    "guilds": [{"name": "Mika", "killFame": 32000}],
                }
            ]
        )

        await auto._run_battle_report_tick(
            bot,
            gi,
            bb,
            now=datetime(2026, 6, 14, 6, 30),
        )

        channel = bot.client.channels.get("battle-channel")
        self.assertEqual(channel.send_count if channel else 0, 0)
        self.assertFalse(repo.has_seen_battle_report("guild", "123"))

    async def test_battle_report_tick_skips_unconfigured_window_and_seen(self):
        repo.bind_guild("guild", "albion-guild", "Mika", "admin")
        repo.set_setting("guild", "battle_report_channel_id", "battle-channel")
        repo.set_setting("guild", "battle_report_min_guild_players", 2)
        bot = FakeBot()
        gi = FakeBattleGameInfo(_battle_detail_with_guild_players(20), _battle_events())
        bb = FakeAlbionBB(
            [{"albionId": "123", "guilds": [{"name": "Mika"}]}]
        )

        await auto._run_battle_report_tick(
            bot,
            gi,
            bb,
            now=datetime(2026, 6, 14, 6, 29),
        )
        self.assertEqual(gi.battles_calls, [])
        self.assertEqual(bb.calls, [])

        await auto._run_battle_report_tick(
            bot,
            gi,
            bb,
            now=datetime(2026, 6, 14, 6, 30),
        )
        await auto._run_battle_report_tick(
            bot,
            gi,
            bb,
            now=datetime(2026, 6, 14, 6, 45),
        )

        self.assertEqual(len(gi.battles_calls), 2)
        self.assertEqual(len(bb.calls), 2)
        self.assertEqual(bot.client.channels["battle-channel"].send_count, 1)

    async def test_battle_report_tick_keeps_unseen_when_send_fails(self):
        repo.bind_guild("guild", "albion-guild", "Mika", "admin")
        repo.set_setting("guild", "battle_report_channel_id", "battle-channel")
        repo.set_setting("guild", "battle_report_min_guild_players", 2)
        bot = FakeBot(fail_send=True)
        gi = FakeBattleGameInfo(_battle_detail_with_guild_players(20), _battle_events())
        bb = FakeAlbionBB(
            [{"albionId": "123", "guilds": [{"name": "Mika"}]}]
        )

        await auto._run_battle_report_tick(
            bot,
            gi,
            bb,
            now=datetime(2026, 6, 14, 6, 30),
        )

        self.assertFalse(repo.has_seen_battle_report("guild", "123"))

    async def test_battle_report_tick_filters_by_guild_and_min_participants(self):
        repo.bind_guild("guild", "albion-guild", "Mika", "admin")
        repo.set_setting("guild", "battle_report_channel_id", "battle-channel")
        repo.set_setting("guild", "battle_report_min_guild_players", 4)
        bot = FakeBot()
        gi = FakeBattleGameInfo(_battle_detail(), _battle_events())
        bb = FakeAlbionBB(
            [
                {"albionId": "123", "guilds": [{"name": "Mika"}]},
                {"albionId": "999", "guilds": [{"name": "Enemy"}]},
            ]
        )

        await auto._run_battle_report_tick(
            bot,
            gi,
            bb,
            now=datetime(2026, 6, 14, 6, 30),
        )

        self.assertEqual(gi.battle_ids, ["123"])
        channel = bot.client.channels.get("battle-channel")
        self.assertEqual(channel.send_count if channel else 0, 0)


def _battle_detail():
    return {
        "id": 123,
        "startTime": "2026-06-14T13:01:13Z",
        "totalPlayers": 6,
        "totalKills": 8,
        "totalFame": 1_234_567,
        "players": {
            "p1": {
                "name": "Alice",
                "guildName": "Mika",
                "allianceName": "5I7",
                "kills": 3,
                "deaths": 0,
                "killFame": 12_000,
            },
            "p2": {
                "name": "Bob",
                "guildName": "Mika",
                "allianceName": "5I7",
                "kills": 1,
                "deaths": 2,
                "killFame": 20_000,
            },
            "p3": {
                "name": "Cathy",
                "guildName": "Mika",
                "allianceName": "5I7",
                "kills": 0,
                "deaths": 1,
                "killFame": 0,
            },
            "p4": {
                "name": "EnemyA",
                "guildName": "CCTV",
                "allianceName": "HDD",
                "kills": 2,
                "deaths": 1,
                "killFame": 30_000,
            },
            "p5": {
                "name": "EnemyB",
                "guildName": "CCTV",
                "allianceName": "HDD",
                "kills": 1,
                "deaths": 2,
                "killFame": 10_000,
            },
            "p6": {
                "name": "EnemyC",
                "guildName": "Nazareno",
                "allianceName": "MONKY",
                "kills": 1,
                "deaths": 2,
                "killFame": 5_000,
            },
        },
        "guilds": {
            "g1": {"name": "Mika", "alliance": "5I7", "killFame": 32_000},
            "g2": {"name": "CCTV", "alliance": "HDD", "killFame": 40_000},
            "g3": {"name": "Nazareno", "alliance": "MONKY", "killFame": 5_000},
        },
        "alliances": {
            "a1": {"name": "5I7", "killFame": 32_000},
            "a2": {"name": "HDD", "killFame": 40_000},
            "a3": {"name": "MONKY", "killFame": 5_000},
        },
    }


def _battle_detail_with_guild_players(count: int):
    detail = _battle_detail()
    players = dict(detail["players"])
    existing = [
        p
        for p in players.values()
        if p.get("guildName") == "Mika" or p.get("GuildName") == "Mika"
    ]
    for idx in range(len(existing) + 1, count + 1):
        players[f"mika-extra-{idx}"] = {
            "name": f"MikaExtra{idx}",
            "guildName": "Mika",
            "allianceName": "5I7",
            "kills": 0,
            "deaths": 0,
            "killFame": 0,
        }
    detail["players"] = players
    detail["totalPlayers"] = len(players)
    return detail


def _battle_events():
    return [
        {
            "TotalVictimKillFame": 400_000,
            "Victim": {"Name": "Bob", "Id": "p2", "GuildName": "Mika"},
        },
        {
            "TotalVictimKillFame": 300_000,
            "Victim": {"Name": "Bob", "Id": "p2", "GuildName": "Mika"},
        },
        {
            "TotalVictimKillFame": 900_000,
            "Victim": {"Name": "Cathy", "Id": "p3", "GuildName": "Mika"},
        },
    ]


class FakeAlbionBB:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def albionbb_get(self, path, params=None, ttl=300):
        self.calls.append(dict(params or {}))
        self.path = path
        return self.rows


class FakeBattleGameInfo:
    def __init__(self, detail, events, battle_rows=None):
        self.detail = detail
        self.events = events
        self.battle_rows = battle_rows
        self.battle_ids = []
        self.battles_calls = []

    async def battles(self, guild_id=None, range_="week", sort="recent", limit=20, offset=0):
        self.battles_calls.append({"guild_id": guild_id, "limit": limit})
        if self.battle_rows is not None:
            return self.battle_rows
        return [{"id": "123"}]

    async def battle(self, battle_id):
        self.battle_ids.append(str(battle_id))
        return self.detail

    async def battle_events(self, battle_id, limit=51, offset=0):
        return self.events


class FakeAIService:
    def __init__(self, summary):
        self.summary = summary
        self.report_calls = []

    async def summarize_battle_report(self, report):
        self.report_calls.append(report)
        return self.summary


class FakeBot:
    def __init__(self, *, fail_send=False, channel_names=None):
        self.client = FakeClient(fail_send=fail_send, channel_names=channel_names)


class FakeClient:
    def __init__(self, *, fail_send=False, channel_names=None):
        self.fail_send = fail_send
        self.channel_names = dict(channel_names or {})
        self.channels = {}

    async def fetch_public_channel(self, channel_id):
        channel = self.channels.get(channel_id)
        if channel is None:
            channel = FakeChannel(
                channel_id=channel_id,
                name=self.channel_names.get(channel_id),
                fail_send=self.fail_send,
            )
            self.channels[channel_id] = channel
        return channel


class FakeChannel:
    def __init__(self, *, channel_id=None, name=None, fail_send=False):
        self.id = channel_id
        self.name = name
        self.fail_send = fail_send
        self.send_count = 0

    async def send(self, message):
        if self.fail_send:
            raise RuntimeError("send failed")
        self.send_count += 1
        self.last_message = message
