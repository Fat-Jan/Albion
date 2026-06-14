import unittest

from bot.cards.query_cards import profile_card


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


class QueryCardTest(unittest.TestCase):
    def test_profile_card_reads_nested_gathering_and_crafting_fame(self):
        card = profile_card(
            {
                "Name": "player",
                "GuildName": "guild",
                "KillFame": 1234,
                "DeathFame": 5678,
                "FameRatio": 1.2,
                "LifetimeStatistics": {
                    "PvE": {"Total": 20000},
                    "Gathering": {"All": {"Total": 844029}},
                    "Crafting": {"Total": 222552866},
                },
            },
            kills=3,
            deaths=4,
        )

        text = card_text(card)

        self.assertIn("PvE 声望 `2.0万`", text)
        self.assertIn("采集声望 `84.4万`", text)
        self.assertIn("制造声望 `2.23亿`", text)
        self.assertNotIn("采集声望 `?`", text)
