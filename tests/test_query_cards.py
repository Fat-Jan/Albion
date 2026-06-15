import unittest

from bot.cards.query_cards import profile_card, valuation_card


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
        sections = section_texts(card)

        self.assertIn("**身份**", text)
        self.assertIn("**战斗**", text)
        self.assertIn("**成长**", text)
        self.assertIn("**近期**", text)
        self.assertGreaterEqual(len(sections), 4)
        self.assertIn("PvE 声望 `2.0万`", text)
        self.assertIn("采集声望 `84.4万`", text)
        self.assertIn("制造声望 `2.23亿`", text)
        self.assertNotIn("采集声望 `?`", text)

    def test_valuation_card_uses_contextual_sections(self):
        card = valuation_card(
            "player",
            {
                "EventId": "12345",
                "TimeStamp": "2026-06-14T10:00:00",
                "Victim": {"AverageItemPower": 1200},
            },
            {
                "items": [
                    {"slot": "MainHand", "type": "T8_MAIN_SPEAR_KEEPER@1", "quality": 4, "count": 1, "value": 1000},
                    {"slot": None, "type": "T4_BAG", "quality": 1, "count": 1, "value": 2000},
                ],
            },
        )

        text = card_text(card)
        sections = section_texts(card)

        self.assertIn("**死亡概况**", text)
        self.assertIn("**损失估值**", text)
        self.assertIn("**明细**", text)
        self.assertTrue(any("装备估值 ≈ `1,000` 银" in s and "背包估值 ≈ `2,000` 银" in s for s in sections))
