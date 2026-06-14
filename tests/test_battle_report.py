import unittest

from bot.albion.battle_report import build_battle_report
from bot.cards.battle_report_cards import battle_report_card


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

    def test_card_marks_participant_counts_and_player_leaders(self):
        report = build_battle_report(
            _battle_detail(),
            _battle_events(),
            guild_name="Mika",
        )

        text = card_text(battle_report_card(report))

        self.assertIn("Mika [5I7]　3人", text)
        self.assertIn("CCTV [HDD]　2人", text)
        self.assertIn("5I7　3人", text)
        self.assertIn("击杀最多：`Alice`　3 次", text)
        self.assertIn("击杀声望最高：`Bob`　`2.0万`", text)
        self.assertIn("阵亡最多：`Bob`　2 次", text)
        self.assertIn("阵亡声望最高：`Cathy`　`90.0万`", text)


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
