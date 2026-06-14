import unittest

from bot.cards.broadcast_cards import kill_card
from bot.cards.query_cards import KILLBOARD_URL


def card_text(card_message) -> str:
    texts = []
    for card in card_message:
        for module in card.get("modules", []):
            text = module.get("text")
            if isinstance(text, dict):
                texts.append(text.get("content", ""))
            elif isinstance(text, str):
                texts.append(text)
    return "\n".join(texts)


def action_buttons(card_message):
    buttons = []
    for card in card_message:
        for module in card.get("modules", []):
            for element in module.get("elements", []) or []:
                if element.get("type") == "button":
                    buttons.append(element)
    return buttons


class BroadcastCardTest(unittest.TestCase):
    def test_death_broadcast_shows_loss_split_and_killboard_link(self):
        event = {
            "EventId": "12345",
            "Killer": {"Name": "killer", "GuildName": "enemy"},
            "Victim": {"Name": "victim", "GuildName": "ours", "AverageItemPower": 1200},
            "TotalVictimKillFame": 150000,
            "TimeStamp": "2026-06-14T10:00:00",
        }
        result = {
            "total": 1000,
            "items": [
                {"slot": "MainHand", "value": 1000},
                {"slot": None, "value": 3000},
            ],
        }

        card = list(kill_card(event, is_kill=False, highlight=True, valuation_result=result))

        text = card_text(card)
        self.assertIn("装备估值 `1,000` 银", text)
        self.assertIn("背包估值 `3,000` 银", text)
        self.assertIn("总损失 `4,000` 银", text)

        buttons = action_buttons(card)
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0]["value"], KILLBOARD_URL.format(eid="12345"))
