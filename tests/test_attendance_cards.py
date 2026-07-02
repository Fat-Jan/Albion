import unittest

from bot.cards.attendance_cards import attendance_card


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


class AttendanceCardTest(unittest.TestCase):
    def test_card_names_snapshot_scope_and_member_rates(self):
        card = attendance_card(
            "Top Squad",
            {
                "battle_count": 20,
                "counted_battle_count": 3,
                "min_guild_players": 20,
                "members": [
                    {
                        "name": "Alice",
                        "participated_battles": 2,
                        "participation_rate": 67,
                        "last_seen_at": "2026-06-24T10:00:00",
                        "kills": 3,
                        "deaths": 1,
                        "kill_fame": 12345,
                    },
                    {
                        "name": "Bob",
                        "participated_battles": 0,
                        "participation_rate": 0,
                    },
                ],
            },
            requested_battles=20,
        )

        text = card_text(card)
        self.assertIn("战斗参与快照", text)
        self.assertIn("不等同正式 CTA 考勤", text)
        self.assertIn("Alice", text)
        self.assertIn("参与 `2` 场", text)
        self.assertIn("参与率 `67%`", text)
        self.assertIn("Bob", text)
        self.assertIn("参与 `0` 场", text)


if __name__ == "__main__":
    unittest.main()
