import os
import tempfile
import unittest

from bot import config
from bot.cards.regear_cards import death_detail_card, regear_apply_card
from bot.commands import regear
from bot.store import repo
from bot.store.db import init_db


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


class RegearFlowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "bot.db")
        init_db()

    def tearDown(self):
        config.DB_PATH = self.old_db
        self.tmp.cleanup()

    def test_regear_schema_has_paid_tracking_columns(self):
        rid = repo.create_regear("guild", "user", "player", "event-1", 100)
        repo.set_regear_status(rid, "approved", "admin")
        repo.set_regear_paid(rid, "payer")

        row = repo.get_regear(rid)

        self.assertEqual(row["status"], "paid")
        self.assertEqual(row["reviewed_by"], "admin")
        self.assertIsNotNone(row["reviewed_at"])
        self.assertEqual(row["paid_by"], "payer")
        self.assertIsNotNone(row["paid_at"])

    def test_guild_binding_has_dedicated_regear_channel_setting(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "approval_channel_id", "bind-approval")
        repo.set_setting("guild", "regear_channel_id", "regear-approval")
        repo.set_setting("guild", "regear_reviewer_role_ids", "role-a,role-b")

        row = repo.get_guild_binding("guild")

        self.assertEqual(row["approval_channel_id"], "bind-approval")
        self.assertEqual(row["regear_channel_id"], "regear-approval")
        self.assertEqual(row["regear_reviewer_role_ids"], "role-a,role-b")

    def test_list_regear_filters_statuses(self):
        pending = repo.create_regear("guild", "user-1", "player-1", "event-1", 100)
        approved = repo.create_regear("guild", "user-2", "player-2", "event-2", 200)
        rejected = repo.create_regear("guild", "user-3", "player-3", "event-3", 300)
        repo.set_regear_status(approved, "approved", "admin")
        repo.set_regear_status(rejected, "rejected", "admin")

        rows = repo.list_regear("guild", statuses=("pending", "approved"))

        self.assertEqual([r["id"] for r in rows], [approved, pending])

    def test_regear_reviewer_request_lifecycle(self):
        rid = repo.create_regear_reviewer_request("guild", "user")
        self.assertIsNotNone(repo.get_open_regear_reviewer_request("guild", "user"))

        repo.set_regear_reviewer_request_message(rid, "msg-1")
        row = repo.get_regear_reviewer_request(rid)
        self.assertEqual(row["message_id"], "msg-1")

        repo.set_regear_reviewer_request_status(rid, "approved", "admin")
        row = repo.get_regear_reviewer_request(rid)
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["reviewed_by"], "admin")
        self.assertIsNotNone(row["reviewed_at"])
        self.assertIsNone(repo.get_open_regear_reviewer_request("guild", "user"))

    async def test_refresh_regear_estimate_updates_stored_value(self):
        rid = repo.create_regear("guild", "user", "player", "event-1", 100)
        gi = FakeGameInfo(
            {
                "EventId": "event-1",
                "Victim": {
                    "Equipment": {
                        "MainHand": {"Type": "T8_MAIN_SPEAR_KEEPER@1", "Quality": 4},
                        "OffHand": {"Type": "T6_OFF_DEMONSKULL_HELL@3", "Quality": 4},
                    }
                },
            }
        )
        market = FakeMarket()

        value = await regear._refresh_regear_estimate(rid, gi, market)

        self.assertEqual(value, 1500)
        self.assertEqual(repo.get_regear(rid)["est_value"], 1500)

    def test_regear_approval_channel_prefers_dedicated_channel(self):
        self.assertEqual(
            regear._regear_approval_channel({"approval_channel_id": "bind", "regear_channel_id": "regear"}),
            "regear",
        )

    def test_regear_approval_channel_falls_back_to_binding_approval_channel(self):
        self.assertEqual(
            regear._regear_approval_channel({"approval_channel_id": "bind", "regear_channel_id": ""}),
            "bind",
        )

    def test_regear_reviewer_role_allows_non_admin_reviewer(self):
        user = FakeUser(["role-b"])
        binding = {"regear_reviewer_role_ids": "role-a,role-b"}

        self.assertTrue(regear._has_regear_reviewer_role(user, binding))

    def test_regear_reviewer_role_rejects_unlisted_user(self):
        user = FakeUser(["other-role"])
        binding = {"regear_reviewer_role_ids": "role-a,role-b"}

        self.assertFalse(regear._has_regear_reviewer_role(user, binding))

    def test_regear_reviewer_role_accepts_single_configured_role(self):
        user = FakeUser(["role-a"])
        binding = {"regear_reviewer_role_ids": "role-a"}

        self.assertTrue(regear._has_regear_reviewer_role(user, binding))

    def test_regear_apply_card_explains_inventory_is_excluded(self):
        event = {
            "TimeStamp": "2026-06-14T10:00:00",
            "Victim": {"AverageItemPower": 1200},
        }

        text = card_text(regear_apply_card(1, "user", "Latano", event, 1165632))

        self.assertIn("补装金额 ≈ 1,165,632 银", text)
        self.assertIn("只计算穿戴装备", text)
        self.assertIn("背包物品不计入补装", text)

    def test_regear_death_detail_card_labels_total_as_regear_amount(self):
        event = {
            "EventId": "12345",
            "TimeStamp": "2026-06-14T10:00:00",
            "Victim": {
                "AverageItemPower": 1200,
                "Equipment": {
                    "MainHand": {"Type": "T8_MAIN_SPEAR_KEEPER@1", "Quality": 4}
                },
            },
            "Killer": {"Name": "killer", "GuildName": "enemy"},
        }
        result = {
            "total": 1000,
            "items": [
                {"slot": "MainHand", "type": "T8_MAIN_SPEAR_KEEPER@1", "quality": 4, "count": 1, "value": 1000},
                {"slot": None, "type": "T8_BAG", "quality": 1, "count": 1, "value": 3000},
            ],
        }

        text = card_text(death_detail_card("Latano", event, result))

        self.assertIn("补装金额 ≈ 1,000 银", text)
        self.assertIn("背包物品不计入补装", text)
        self.assertNotIn("总估值", text)


class FakeGameInfo:
    def __init__(self, event):
        self.event_data = event

    async def event(self, event_id):
        return self.event_data


class FakeMarket:
    async def history(self, items, locations=None, qualities=None, time_scale=24):
        return [
            {
                "item_id": "T8_MAIN_SPEAR_KEEPER@1",
                "quality": 4,
                "location": "Caerleon",
                "data": [{"avg_price": 1000}],
            },
            {
                "item_id": "T6_OFF_DEMONSKULL_HELL@3",
                "quality": 4,
                "location": "Caerleon",
                "data": [{"avg_price": 500}],
            },
        ]

    async def prices(self, items, locations=None, qualities=None):
        return []


class FakeUser:
    def __init__(self, roles):
        self.roles = roles
