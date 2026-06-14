import os
import tempfile
import unittest
from datetime import datetime, timedelta

from bot import config
from bot.cards.regear_cards import death_detail_card, death_select_card, regear_apply_card
from bot.commands import admin, regear
from bot.tasks import auto
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
        repo.set_setting("guild", "regear_apply_channel_id", "regear-apply")
        repo.set_setting("guild", "regear_review_channel_id", "regear-review")
        repo.set_setting("guild", "regear_payout_channel_id", "regear-payout")
        repo.set_setting("guild", "regear_notify_channel_id", "regear-notify")
        repo.set_setting("guild", "member_change_channel_id", "member-change")
        repo.set_setting("guild", "regear_reviewer_role_ids", "role-a,role-b")

        row = repo.get_guild_binding("guild")

        self.assertEqual(row["approval_channel_id"], "bind-approval")
        self.assertEqual(row["regear_channel_id"], "regear-approval")
        self.assertEqual(row["regear_apply_channel_id"], "regear-apply")
        self.assertEqual(row["regear_review_channel_id"], "regear-review")
        self.assertEqual(row["regear_payout_channel_id"], "regear-payout")
        self.assertEqual(row["regear_notify_channel_id"], "regear-notify")
        self.assertEqual(row["member_change_channel_id"], "member-change")
        self.assertEqual(row["regear_reviewer_role_ids"], "role-a,role-b")

    def test_guild_binding_has_split_broadcast_channel_settings(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "kill_broadcast_channel_id", "kill-broadcast")
        repo.set_setting("guild", "death_broadcast_channel_id", "death-broadcast")

        row = repo.get_guild_binding("guild")

        self.assertEqual(row["kill_broadcast_channel_id"], "kill-broadcast")
        self.assertEqual(row["death_broadcast_channel_id"], "death-broadcast")

    def test_death_broadcast_channel_uses_split_channels_with_legacy_fallback(self):
        binding = {
            "broadcast_channel_id": "legacy",
            "kill_broadcast_channel_id": "kills",
            "death_broadcast_channel_id": "deaths",
        }

        self.assertEqual(auto._broadcast_channel_for_event(binding, is_kill=True, is_death=False), "kills")
        self.assertEqual(auto._broadcast_channel_for_event(binding, is_kill=False, is_death=True), "deaths")
        self.assertEqual(
            auto._broadcast_channel_for_event(
                {
                    "broadcast_channel_id": "legacy",
                    "kill_broadcast_channel_id": "",
                    "death_broadcast_channel_id": None,
                },
                is_kill=True,
                is_death=False,
            ),
            "legacy",
        )

    def test_broadcast_classify_filters_zero_fame_events(self):
        event = {
            "TotalVictimKillFame": 0,
            "Killer": {"GuildId": "guild"},
            "Victim": {"GuildId": "enemy"},
        }

        self.assertEqual(auto.classify(event, "guild"), (False, False))

    def test_broadcast_classify_keeps_positive_fame_events(self):
        event = {
            "TotalVictimKillFame": 1,
            "Killer": {"GuildId": "guild"},
            "Victim": {"GuildId": "enemy"},
        }

        self.assertEqual(auto.classify(event, "guild"), (True, False))

    def test_member_review_channel_prefers_dedicated_member_change_channel(self):
        self.assertEqual(
            auto._member_review_notify_channel(
                {
                    "approval_channel_id": "approval",
                    "broadcast_channel_id": "broadcast",
                    "member_change_channel_id": "member-change",
                }
            ),
            "member-change",
        )

    def test_member_review_channel_falls_back_to_broadcast_then_approval(self):
        self.assertEqual(
            auto._member_review_notify_channel(
                {
                    "approval_channel_id": "approval",
                    "broadcast_channel_id": "broadcast",
                    "member_change_channel_id": "",
                }
            ),
            "broadcast",
        )
        self.assertEqual(
            auto._member_review_notify_channel(
                {
                    "approval_channel_id": "approval",
                    "broadcast_channel_id": "",
                    "member_change_channel_id": None,
                }
            ),
            "approval",
        )

    def test_death_broadcast_interval_uses_shorter_evening_window(self):
        self.assertEqual(auto._death_broadcast_interval_seconds(datetime(2026, 6, 14, 19, 59)), 240)
        self.assertEqual(auto._death_broadcast_interval_seconds(datetime(2026, 6, 14, 20, 0)), 90)
        self.assertEqual(auto._death_broadcast_interval_seconds(datetime(2026, 6, 14, 23, 59)), 90)
        self.assertEqual(auto._death_broadcast_interval_seconds(datetime(2026, 6, 15, 0, 29)), 90)
        self.assertEqual(auto._death_broadcast_interval_seconds(datetime(2026, 6, 15, 0, 30)), 240)

    def test_death_broadcast_throttle_uses_current_interval(self):
        normal_now = datetime(2026, 6, 14, 19, 0)
        busy_now = datetime(2026, 6, 14, 21, 0)

        self.assertFalse(auto._should_run_death_broadcast(normal_now, normal_now - timedelta(minutes=3, seconds=59)))
        self.assertTrue(auto._should_run_death_broadcast(normal_now, normal_now - timedelta(minutes=4)))
        self.assertFalse(auto._should_run_death_broadcast(busy_now, busy_now - timedelta(seconds=89)))
        self.assertTrue(auto._should_run_death_broadcast(busy_now, busy_now - timedelta(seconds=90)))
        self.assertTrue(auto._should_run_death_broadcast(busy_now, busy_now - timedelta(seconds=90) + timedelta(microseconds=1)))

    def test_list_regear_filters_statuses(self):
        pending = repo.create_regear("guild", "user-1", "player-1", "event-1", 100)
        approved = repo.create_regear("guild", "user-2", "player-2", "event-2", 200)
        rejected = repo.create_regear("guild", "user-3", "player-3", "event-3", 300)
        repo.set_regear_status(approved, "approved", "admin")
        repo.set_regear_status(rejected, "rejected", "admin")

        rows = repo.list_regear("guild", statuses=("pending", "approved"))

        self.assertEqual([r["id"] for r in rows], [approved, pending])

    def test_list_user_regear_only_returns_that_members_requests(self):
        first = repo.create_regear("guild", "user-1", "player-1", "event-1", 100)
        repo.create_regear("guild", "user-2", "player-2", "event-2", 200)
        second = repo.create_regear("guild", "user-1", "player-1", "event-3", 300)

        rows = repo.list_user_regear("guild", "user-1", limit=5)

        self.assertEqual([r["id"] for r in rows], [second, first])

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
            regear._regear_review_channel(
                {
                    "approval_channel_id": "bind",
                    "regear_channel_id": "legacy",
                    "regear_review_channel_id": "review",
                }
            ),
            "review",
        )

    def test_regear_approval_channel_falls_back_to_binding_approval_channel(self):
        self.assertEqual(
            regear._regear_review_channel(
                {
                    "approval_channel_id": "bind",
                    "regear_channel_id": "",
                    "regear_review_channel_id": "",
                }
            ),
            "bind",
        )

    def test_regear_channel_routes_use_split_channels_with_legacy_fallbacks(self):
        binding = {
            "approval_channel_id": "bind",
            "regear_channel_id": "legacy",
            "regear_apply_channel_id": "apply",
            "regear_review_channel_id": "review",
            "regear_payout_channel_id": "payout",
            "regear_notify_channel_id": "notify",
        }

        self.assertEqual(regear._regear_apply_channel(binding), "apply")
        self.assertEqual(regear._regear_review_channel(binding), "review")
        self.assertEqual(regear._regear_payout_channel(binding), "payout")
        self.assertEqual(regear._regear_notify_channel(binding), "notify")
        self.assertEqual(
            regear._regear_payout_channel({"approval_channel_id": "bind", "regear_channel_id": "legacy"}),
            "legacy",
        )
        self.assertEqual(
            regear._regear_notify_channel({"approval_channel_id": "bind", "regear_channel_id": "legacy"}),
            "legacy",
        )

    def test_regear_paid_notice_keeps_public_notification_clean(self):
        row = {"id": 123, "kook_user_id": "user-1", "est_value": 999999, "event_id": "event-1"}

        text = regear._regear_paid_notice(row)

        self.assertIn("(met)user-1(met)", text)
        self.assertIn("#123", text)
        self.assertIn("已完成", text)
        self.assertNotIn("999", text)
        self.assertNotIn("event-1", text)

    def test_admin_usage_includes_split_regear_center_commands(self):
        self.assertIn("/设置 补装初始化频道", admin.SETTING_USAGE)
        self.assertIn("/设置 补装申请频道 #频道", admin.SETTING_USAGE)
        self.assertIn("/设置 补装审核频道 #频道", admin.SETTING_USAGE)
        self.assertIn("/设置 补装发放频道 #频道", admin.SETTING_USAGE)
        self.assertIn("/设置 补装通知频道 #频道", admin.SETTING_USAGE)

    def test_regear_center_default_names_use_emoji(self):
        self.assertEqual(admin.REGEAR_CENTER_CATEGORY_NAME, "🛡️补装中心")
        self.assertEqual(admin.REGEAR_CENTER_CHANNELS["regear_apply_channel_id"], "📥补装申请")
        self.assertEqual(admin.REGEAR_CENTER_CHANNELS["regear_review_channel_id"], "🔍补装审核")
        self.assertEqual(admin.REGEAR_CENTER_CHANNELS["regear_payout_channel_id"], "💰补装发放")
        self.assertEqual(admin.REGEAR_CENTER_CHANNELS["regear_notify_channel_id"], "📣补装通知")

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

    def test_regear_death_select_card_shows_estimate_and_mainhand(self):
        event = {
            "EventId": "event-1",
            "TimeStamp": "2026-06-14T10:00:00",
            "Victim": {
                "AverageItemPower": 1200,
                "Equipment": {
                    "MainHand": {"Type": "T8_MAIN_SPEAR_KEEPER@1", "Quality": 4}
                },
            },
            "Killer": {"Name": "killer"},
        }

        text = card_text(death_select_card("Latano", [event], estimates={"event-1": 1165632}))

        self.assertIn("装备估价 ≈ `1,165,632` 银", text)
        self.assertIn("装备：主手 `T8.1`", text)

    async def test_regear_death_candidate_estimates_use_equipped_total(self):
        deaths = [
            {
                "EventId": "event-1",
                "Victim": {
                    "Equipment": {
                        "MainHand": {"Type": "T8_MAIN_SPEAR_KEEPER@1", "Quality": 4},
                        "OffHand": {"Type": "T6_OFF_DEMONSKULL_HELL@3", "Quality": 4},
                    }
                },
            }
        ]

        estimates = await regear._estimate_death_candidates(deaths, FakeMarket())

        self.assertEqual(estimates, {"event-1": 1500})


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
