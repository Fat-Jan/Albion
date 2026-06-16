import os
import tempfile
import unittest
from datetime import datetime, timedelta

from bot import config
from bot.cards.query_cards import KILLBOARD_URL
from bot.cards.regear_cards import (
    death_detail_card,
    death_select_card,
    regear_apply_card,
    regear_approved_card,
    regear_notice_card,
    regear_queue_card,
    regear_reviewer_apply_card,
    regear_reviewer_result_card,
)
from bot.commands import admin, regear
from khl import api
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


def section_texts(card_message) -> list[str]:
    texts = []
    for card in card_message:
        for module in card.get("modules", []):
            if module.get("type") != "section":
                continue
            text = module.get("text")
            if isinstance(text, dict):
                texts.append(text.get("content", ""))
            elif isinstance(text, str):
                texts.append(text)
    return texts


def card_buttons(card_message) -> list[dict]:
    buttons = []
    for card in card_message:
        for module in card.get("modules", []):
            buttons.extend(
                e for e in module.get("elements", []) if isinstance(e, dict) and e.get("type") == "button"
            )
    return buttons


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
        repo.set_regear_paid(rid, "payer", "silver", "等额银币")

        row = repo.get_regear(rid)

        self.assertEqual(row["status"], "paid")
        self.assertEqual(row["reviewed_by"], "admin")
        self.assertIsNotNone(row["reviewed_at"])
        self.assertEqual(row["paid_by"], "payer")
        self.assertIsNotNone(row["paid_at"])
        self.assertEqual(row["payout_method"], "silver")
        self.assertEqual(row["payout_note"], "等额银币")

    def test_regear_schema_records_reject_reason(self):
        rid = repo.create_regear("guild", "user", "player", "event-1", 100)

        repo.set_regear_rejected(rid, "admin", "重复申请")

        row = repo.get_regear(rid)
        self.assertEqual(row["status"], "rejected")
        self.assertEqual(row["reviewed_by"], "admin")
        self.assertIsNotNone(row["reviewed_at"])
        self.assertEqual(row["reject_reason"], "重复申请")

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
        repo.set_setting("guild", "battle_report_channel_id", "battle-report")

        row = repo.get_guild_binding("guild")

        self.assertEqual(row["kill_broadcast_channel_id"], "kill-broadcast")
        self.assertEqual(row["death_broadcast_channel_id"], "death-broadcast")
        self.assertEqual(row["battle_report_channel_id"], "battle-report")

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

    async def test_broadcast_highlight_requires_fame_over_one_million(self):
        message = await self._run_death_broadcast(
            _broadcast_event(fame=1_000_000, victim_guild_id="guild"),
            FakeBroadcastMarket(loss_total=10_000_000),
        )

        self.assertNotIn("大额损失", card_text(message))

        message = await self._run_death_broadcast(
            _broadcast_event("event-2", fame=1_000_001, victim_guild_id="guild"),
            FakeBroadcastMarket(loss_total=10_000_000),
        )

        self.assertIn("大额损失", card_text(message))

    async def test_broadcast_highlight_accepts_loss_over_ten_million(self):
        message = await self._run_death_broadcast(
            _broadcast_event(fame=150_000, victim_guild_id="guild"),
            FakeBroadcastMarket(loss_total=10_000_000),
        )

        self.assertNotIn("大额损失", card_text(message))

        message = await self._run_death_broadcast(
            _broadcast_event("event-2", fame=150_000, victim_guild_id="guild"),
            FakeBroadcastMarket(loss_total=10_000_001),
        )

        self.assertIn("大额损失", card_text(message))

    async def test_broadcast_kill_highlight_requires_fame_over_one_million(self):
        message = await self._run_death_broadcast(
            _broadcast_event(fame=1_000_000, killer_guild_id="guild"),
            FakeBroadcastMarket(loss_total=10_000_000),
        )

        self.assertNotIn("大额！", card_text(message))

        message = await self._run_death_broadcast(
            _broadcast_event("event-2", fame=1_000_001, killer_guild_id="guild"),
            FakeBroadcastMarket(loss_total=0),
        )

        self.assertIn("大额！", card_text(message))

    async def test_broadcast_kill_highlight_accepts_loss_over_ten_million(self):
        message = await self._run_death_broadcast(
            _broadcast_event(fame=150_000, killer_guild_id="guild"),
            FakeBroadcastMarket(loss_total=10_000_001),
        )

        text = card_text(message)
        self.assertIn("大额！", text)
        self.assertIn("总损失 `1000.0万` 银", text)

    async def _run_death_broadcast(self, event: dict, market) -> object:
        repo.bind_guild("guild", "guild", "Albion Guild", "admin")
        repo.set_setting("guild", "broadcast_channel_id", "broadcast")
        repo.set_setting("guild", "kill_fame_threshold", 100_000)
        auto._primed = True
        auto._seen.clear()
        auto._seen_order.clear()
        auto._last_death_broadcast_at = None
        channels = {"broadcast": FakeChannel("broadcast")}
        bot = FakeScheduledBot(channels)
        auto.register(bot, FakeBroadcastGameInfo([event]), market)

        await bot.task.interval_tasks["death_broadcast"]()

        return channels["broadcast"].messages[-1]

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

    def test_regear_reviewer_result_card_shows_request_id_and_status(self):
        row = {
            "id": 12,
            "kook_user_id": "user-1",
            "status": "approved",
            "created_at": "2026-06-15 09:00:00",
            "reviewed_at": "2026-06-15 10:16:51",
            "reviewed_by": "admin",
        }

        text = card_text(regear_reviewer_result_card(row))

        self.assertIn("补装审核身份申请 `#12` 已通过", text)
        self.assertIn("(met)user-1(met)", text)
        self.assertIn("当前状态：`已通过`", text)
        self.assertIn("申请时间：`2026-06-15 17:00:00 北京时间`", text)
        self.assertIn("审核时间：`2026-06-15 18:16:51 北京时间`", text)

    def test_regear_reviewer_apply_card_shows_request_id_and_pending_status(self):
        text = card_text(regear_reviewer_apply_card(12, "user-1"))

        self.assertIn("申请号：`#12`", text)
        self.assertIn("当前状态：`待审批`", text)
        self.assertIn("(met)user-1(met)", text)

    async def test_regear_reviewer_request_approval_notifies_and_updates_original_card(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "approval_channel_id", "approval")
        repo.set_setting("guild", "member_change_channel_id", "member-change")
        repo.set_setting("guild", "regear_reviewer_role_ids", "reviewer")
        rid = repo.create_regear_reviewer_request("guild", "user-1")
        repo.set_regear_reviewer_request_message(rid, "msg-reviewer-1")
        channels = {"approval": FakeChannel("approval"), "member-change": FakeChannel("member-change")}
        guild = FakeGuild(FakeUser([], user_id="owner"))
        bot = FakeBot(channels, guild)

        await regear._handle_reviewer_request_review(
            bot,
            "regear_reviewer_approve",
            {"rid": rid},
            "guild",
            "owner",
            channels["approval"],
        )

        row = repo.get_regear_reviewer_request(rid)
        self.assertEqual(row["status"], "approved")
        self.assertEqual(guild.granted_roles, [("user-1", "reviewer")])
        self.assertEqual(len(channels["member-change"].messages), 1)
        notice = card_text(channels["member-change"].messages[0])
        self.assertIn("补装审核身份申请 `#1` 已通过", notice)
        self.assertIn("(met)user-1(met)", notice)
        updates = [req for req in bot.client.gate.requests if req.route == "message/update"]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].params["json"]["msg_id"], "msg-reviewer-1")
        self.assertIn("当前状态：`已通过`", updates[0].params["json"]["content"])

    async def test_regear_reviewer_request_rejection_notifies_and_updates_original_card(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "approval_channel_id", "approval")
        repo.set_setting("guild", "member_change_channel_id", "member-change")
        repo.set_setting("guild", "regear_reviewer_role_ids", "reviewer")
        rid = repo.create_regear_reviewer_request("guild", "user-1")
        repo.set_regear_reviewer_request_message(rid, "msg-reviewer-1")
        channels = {"approval": FakeChannel("approval"), "member-change": FakeChannel("member-change")}
        bot = FakeBot(channels, FakeGuild(FakeUser([], user_id="owner")))

        await regear._handle_reviewer_request_review(
            bot,
            "regear_reviewer_reject",
            {"rid": rid},
            "guild",
            "owner",
            channels["approval"],
        )

        row = repo.get_regear_reviewer_request(rid)
        self.assertEqual(row["status"], "rejected")
        self.assertEqual(len(channels["member-change"].messages), 1)
        notice = card_text(channels["member-change"].messages[0])
        self.assertIn("补装审核身份申请 `#1` 已拒绝", notice)
        self.assertIn("当前状态：`已拒绝`", notice)
        updates = [req for req in bot.client.gate.requests if req.route == "message/update"]
        self.assertEqual(len(updates), 1)
        self.assertIn("当前状态：`已拒绝`", updates[0].params["json"]["content"])

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
        row = {
            "id": 123,
            "kook_user_id": "user-1",
            "est_value": 999999,
            "event_id": "event-1",
            "status": "paid",
            "paid_at": "2026-06-15 12:00:00",
            "payout_method": "silver",
        }

        text = regear._regear_paid_notice(row)

        self.assertIn("(met)user-1(met)", text)
        self.assertIn("#123", text)
        self.assertIn("已发放", text)
        self.assertIn("处理时间", text)
        self.assertIn("2026-06-15 20:00:00 北京时间", text)
        self.assertIn("等额银币", text)
        self.assertNotIn("999", text)
        self.assertNotIn("event-1", text)

    def test_regear_rejected_notice_mentions_reason_and_user(self):
        row = {"id": 123, "kook_user_id": "user-1", "status": "rejected", "reject_reason": "重复申请"}

        text = regear._regear_rejected_notice(row)

        self.assertIn("(met)user-1(met)", text)
        self.assertIn("#123", text)
        self.assertIn("已拒绝", text)
        self.assertIn("重复申请", text)

    async def test_regear_approve_sends_status_notice_with_details_to_applicant(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "regear_reviewer_role_ids", "reviewer")
        repo.set_setting("guild", "regear_payout_channel_id", "payout")
        repo.set_setting("guild", "regear_notify_channel_id", "notify")
        rid = repo.create_regear("guild", "user-1", "player-1", "event-1", 100)
        channels = {"review": FakeChannel("review"), "payout": FakeChannel("payout"), "notify": FakeChannel("notify")}
        bot = FakeBot(channels, FakeGuild(FakeUser(["reviewer"], user_id="reviewer-user")))

        await regear._handle_review(
            bot,
            FakeGameInfo(sample_regear_event("event-1")),
            FakeMarket(),
            "regear_approve",
            {"rid": rid},
            "guild",
            "reviewer-user",
            channels["review"],
        )

        row = repo.get_regear(rid)
        self.assertEqual(row["status"], "approved")
        self.assertTrue(any("已通过" in str(m) and "已转到发放频道" in str(m) for m in channels["review"].messages))
        self.assertEqual(len(channels["payout"].messages), 1)
        self.assertEqual(len(channels["notify"].messages), 1)
        notice = channels["notify"].messages[0]
        text = card_text(notice)
        buttons = card_buttons(notice)
        self.assertIn("补装申请 `#1` 已通过", text)
        self.assertIn("(met)user-1(met)", text)
        self.assertIn("当前状态：`待发放`", text)
        self.assertIn("补装金额 ≈ `1,500` 银", text)
        self.assertIn("**装备明细**", text)
        self.assertIn("T8.1", text)
        self.assertTrue(any(b["value"] == KILLBOARD_URL.format(eid="event-1") for b in buttons))

    async def test_regear_approve_updates_original_review_card_status(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "regear_reviewer_role_ids", "reviewer")
        rid = repo.create_regear("guild", "user-1", "player-1", "event-1", 100)
        repo.set_regear_message(rid, "msg-review-1")
        channel = FakeChannel("review")
        bot = FakeBot({"review": channel}, FakeGuild(FakeUser(["reviewer"], user_id="reviewer-user")))

        await regear._handle_review(
            bot,
            FakeGameInfo(sample_regear_event("event-1")),
            FakeMarket(),
            "regear_approve",
            {"rid": rid},
            "guild",
            "reviewer-user",
            channel,
        )

        updates = [req for req in bot.client.gate.requests if req.route == "message/update"]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].params["json"]["msg_id"], "msg-review-1")
        content = updates[0].params["json"]["content"]
        self.assertIn("补装申请 `#1` 已通过", content)
        self.assertIn("当前状态：`待发放`", content)

    async def test_regear_reject_sends_status_notice_with_reason_and_details(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "regear_reviewer_role_ids", "reviewer")
        repo.set_setting("guild", "regear_notify_channel_id", "notify")
        rid = repo.create_regear("guild", "user-1", "player-1", "event-1", 100)
        channels = {"review": FakeChannel("review"), "notify": FakeChannel("notify")}
        bot = FakeBot(channels, FakeGuild(FakeUser(["reviewer"], user_id="reviewer-user")))

        await regear._handle_review(
            bot,
            FakeGameInfo(sample_regear_event("event-1")),
            FakeMarket(),
            "regear_reject",
            {"rid": rid, "reason": "装备/金额异常"},
            "guild",
            "reviewer-user",
            channels["review"],
        )

        self.assertEqual(repo.get_regear(rid)["status"], "rejected")
        self.assertEqual(len(channels["notify"].messages), 1)
        notice = channels["notify"].messages[0]
        text = card_text(notice)
        self.assertIn("补装申请 `#1` 已拒绝", text)
        self.assertIn("当前状态：`已拒绝`", text)
        self.assertIn("原因：`装备/金额异常`", text)
        self.assertIn("**装备明细**", text)
        self.assertIn("T6.3", text)
        self.assertTrue(any(b["value"] == KILLBOARD_URL.format(eid="event-1") for b in card_buttons(notice)))

    async def test_regear_reject_updates_original_review_card_status(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "regear_reviewer_role_ids", "reviewer")
        rid = repo.create_regear("guild", "user-1", "player-1", "event-1", 100)
        repo.set_regear_message(rid, "msg-review-1")
        channel = FakeChannel("review")
        bot = FakeBot({"review": channel}, FakeGuild(FakeUser(["reviewer"], user_id="reviewer-user")))

        await regear._handle_review(
            bot,
            FakeGameInfo(sample_regear_event("event-1")),
            FakeMarket(),
            "regear_reject",
            {"rid": rid, "reason": "非补装范围"},
            "guild",
            "reviewer-user",
            channel,
        )

        updates = [req for req in bot.client.gate.requests if req.route == "message/update"]
        self.assertEqual(len(updates), 1)
        content = updates[0].params["json"]["content"]
        self.assertIn("补装申请 `#1` 已拒绝", content)
        self.assertIn("原因：`非补装范围`", content)

    async def test_regear_paid_sends_status_notice_with_method_and_details(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "regear_reviewer_role_ids", "reviewer")
        repo.set_setting("guild", "regear_notify_channel_id", "notify")
        rid = repo.create_regear("guild", "user-1", "player-1", "event-1", 100)
        repo.set_regear_status(rid, "approved", "admin")
        channels = {"payout": FakeChannel("payout"), "notify": FakeChannel("notify")}
        bot = FakeBot(channels, FakeGuild(FakeUser(["reviewer"], user_id="reviewer-user")))

        await regear._handle_review(
            bot,
            FakeGameInfo(sample_regear_event("event-1")),
            FakeMarket(),
            "regear_paid",
            {"rid": rid, "method": "equipment"},
            "guild",
            "reviewer-user",
            channels["payout"],
        )

        row = repo.get_regear(rid)
        self.assertEqual(row["status"], "paid")
        self.assertEqual(row["payout_method"], "equipment")
        self.assertEqual(len(channels["notify"].messages), 1)
        notice = channels["notify"].messages[0]
        text = card_text(notice)
        self.assertIn("补装申请 `#1` 已发放", text)
        self.assertIn("当前状态：`已发放`", text)
        self.assertIn("发放方式：`原样装备`", text)
        self.assertIn("**装备明细**", text)
        self.assertIn("T8.1", text)
        self.assertTrue(any(b["value"] == KILLBOARD_URL.format(eid="event-1") for b in card_buttons(notice)))

    async def test_regear_pick_submit_reply_includes_request_id(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "regear_review_channel_id", "review")
        repo.set_player_binding("user-1", "guild", "player-1", "Latano")
        channels = {"apply": FakeChannel("apply"), "review": FakeChannel("review")}
        bot = FakeBot(channels, FakeGuild(FakeUser([], user_id="user-1")))

        await regear._handle_pick(
            bot,
            FakeGameInfo(sample_regear_event("event-1")),
            FakeMarket(),
            {"eid": "event-1"},
            "guild",
            "user-1",
            channels["apply"],
        )

        self.assertIn("#1", channels["apply"].messages[-1])
        self.assertIn("已提交补装申请", channels["apply"].messages[-1])

    async def test_regear_pick_review_card_includes_ai_review_hint_when_available(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "regear_review_channel_id", "review")
        repo.set_player_binding("user-1", "guild", "player-1", "Latano")
        channels = {"apply": FakeChannel("apply"), "review": FakeChannel("review")}
        bot = FakeBot(channels, FakeGuild(FakeUser([], user_id="user-1")))
        ai_service = FakeAIService("AI 参考：主手和副手价格正常；背包不计补装。")

        await regear._handle_pick(
            bot,
            FakeGameInfo(sample_regear_event("event-1")),
            FakeMarket(),
            {"eid": "event-1"},
            "guild",
            "user-1",
            channels["apply"],
            ai_service=ai_service,
        )

        review_text = card_text(channels["review"].messages[0])
        self.assertEqual(ai_service.regear_calls[0]["request"]["id"], 1)
        self.assertIn("**AI 审核提示**", review_text)
        self.assertIn("主手和副手价格正常", review_text)

    async def test_regear_processed_click_reports_current_status(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "regear_reviewer_role_ids", "reviewer")
        rid = repo.create_regear("guild", "user-1", "player-1", "event-1", 100)
        repo.set_regear_rejected(rid, "admin", "重复申请")
        channel = FakeChannel("review")
        bot = FakeBot({"review": channel}, FakeGuild(FakeUser(["reviewer"], user_id="reviewer-user")))

        await regear._handle_review(
            bot,
            FakeGameInfo(sample_regear_event("event-1")),
            FakeMarket(),
            "regear_approve",
            {"rid": rid},
            "guild",
            "reviewer-user",
            channel,
        )

        self.assertEqual(len(channel.messages), 1)
        self.assertIn("已拒绝", channel.messages[0])
        self.assertIn("重复申请", channel.messages[0])
        self.assertNotIn("已处理或失效", channel.messages[0])

    def test_admin_usage_includes_split_regear_center_commands(self):
        self.assertIn("/设置 补装初始化频道", admin.SETTING_USAGE)
        self.assertIn("/设置 补装申请频道 #频道", admin.SETTING_USAGE)
        self.assertIn("/设置 补装审核频道 #频道", admin.SETTING_USAGE)
        self.assertIn("/设置 补装发放频道 #频道", admin.SETTING_USAGE)
        self.assertIn("/设置 补装通知频道 #频道", admin.SETTING_USAGE)
        self.assertIn("/设置 战报推送频道 #频道", admin.SETTING_USAGE)
        self.assertIn("/设置 战报本会最小人数 <人数>", admin.SETTING_USAGE)
        self.assertNotIn("/设置 大额阈值", admin.SETTING_USAGE)

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
            "EventId": "12345",
            "TimeStamp": "2026-06-14T10:00:00",
            "TotalVictimKillFame": 99000,
            "numberOfParticipants": 3,
            "Victim": {
                "AverageItemPower": 1200,
                "Equipment": {
                    "MainHand": {"Type": "T8_MAIN_SPEAR_KEEPER@1", "Quality": 4}
                },
            },
            "Killer": {"Name": "killer", "GuildName": "enemy"},
        }
        result = {
            "total": 1165632,
            "items": [
                {"slot": "MainHand", "type": "T8_MAIN_SPEAR_KEEPER@1", "quality": 4, "count": 1, "value": 1165632},
            ],
        }

        card = regear_apply_card(1, "user", "Latano", event, 1165632, result)
        text = card_text(card)
        sections = section_texts(card)
        buttons = card_buttons(card)

        self.assertIn("**审核事项**", text)
        self.assertIn("**死亡事件**", text)
        self.assertIn("**补装口径**", text)
        self.assertIn("**装备明细**", text)
        self.assertTrue(any("申请号：`#1`" in s and "角色：`Latano`" in s for s in sections))
        self.assertIn("当前状态：`待审批`", text)
        self.assertIn("补装金额 ≈ 1,165,632 银", text)
        self.assertIn("只计算穿戴装备", text)
        self.assertIn("背包物品不计入补装", text)
        self.assertIn("被 `killer` [enemy] 击杀", text)
        self.assertIn("击杀声望", text)
        self.assertIn("参与人数", text)
        self.assertIn("T8.1", text)
        self.assertTrue(any(b["value"] == KILLBOARD_URL.format(eid="12345") for b in buttons))
        self.assertTrue(any("重复申请" in b.get("value", "") for b in buttons))
        self.assertTrue(any("非补装范围" in b.get("value", "") for b in buttons))

    def test_regear_approved_card_shows_details_and_payout_methods(self):
        row = {
            "id": 123,
            "kook_user_id": "user-1",
            "event_id": "12345",
            "est_value": 1165632,
            "created_at": "2026-06-14 10:01:00",
            "reviewed_at": "2026-06-14 10:02:00",
            "reviewed_by": "admin",
        }
        event = {
            "EventId": "12345",
            "TimeStamp": "2026-06-14T10:00:00",
            "TotalVictimKillFame": 99000,
            "numberOfParticipants": 3,
            "Victim": {
                "AverageItemPower": 1200,
                "Equipment": {
                    "MainHand": {"Type": "T8_MAIN_SPEAR_KEEPER@1", "Quality": 4}
                },
            },
            "Killer": {"Name": "killer", "GuildName": "enemy"},
        }
        result = {
            "total": 1165632,
            "items": [
                {"slot": "MainHand", "type": "T8_MAIN_SPEAR_KEEPER@1", "quality": 4, "count": 1, "value": 1165632},
            ],
        }

        card = regear_approved_card(row, event, result)
        text = card_text(card)
        sections = section_texts(card)
        buttons = card_buttons(card)

        self.assertIn("补装已通过，等待发放", text)
        self.assertIn("**发放事项**", text)
        self.assertIn("**死亡事件**", text)
        self.assertIn("**装备明细**", text)
        self.assertTrue(any("当前状态：`待发放`" in s and "金额 ≈ `1,165,632` 银" in s for s in sections))
        self.assertIn("审核时间", text)
        self.assertIn("被 `killer` [enemy] 击杀", text)
        self.assertIn("T8.1", text)
        self.assertTrue(any(b["value"] == KILLBOARD_URL.format(eid="12345") for b in buttons))
        self.assertTrue(any('"method": "silver"' in b.get("value", "") for b in buttons))
        self.assertTrue(any('"method": "equipment"' in b.get("value", "") for b in buttons))
        self.assertTrue(any('"method": "item"' in b.get("value", "") for b in buttons))

    def test_regear_queue_card_paid_shortcuts_include_all_payout_methods(self):
        card = regear_queue_card(
            "补装待发放",
            [{"id": 123, "status": "approved", "kook_user_id": "user-1", "est_value": 1000, "event_id": "event-1"}],
        )
        buttons = card_buttons(card)

        self.assertTrue(any('"method": "silver"' in b.get("value", "") for b in buttons))
        self.assertTrue(any('"method": "equipment"' in b.get("value", "") for b in buttons))
        self.assertTrue(any('"method": "item"' in b.get("value", "") for b in buttons))

    def test_regear_processed_text_includes_status_time_and_reason_or_method(self):
        rejected = {
            "id": 1,
            "status": "rejected",
            "kook_user_id": "user-1",
            "reviewed_at": "2026-06-15 10:00:00",
            "reviewed_by": "admin",
            "reject_reason": "装备异常",
        }
        paid = {
            "id": 2,
            "status": "paid",
            "kook_user_id": "user-2",
            "paid_at": "2026-06-15 11:00:00",
            "paid_by": "payer",
            "payout_method": "equipment",
        }

        self.assertIn("已拒绝", regear._regear_processed_text(rejected))
        self.assertIn("装备异常", regear._regear_processed_text(rejected))
        self.assertIn("2026-06-15 18:00:00 北京时间", regear._regear_processed_text(rejected))
        self.assertIn("已发放", regear._regear_processed_text(paid))
        self.assertIn("原样装备", regear._regear_processed_text(paid))
        self.assertIn("2026-06-15 19:00:00 北京时间", regear._regear_processed_text(paid))

    def test_regear_status_text_includes_processing_details(self):
        rows = [
            {
                "id": 1,
                "status": "paid",
                "est_value": 1000,
                "paid_at": "2026-06-15 11:00:00",
                "payout_method": "silver",
            },
            {
                "id": 2,
                "status": "rejected",
                "est_value": 2000,
                "reviewed_at": "2026-06-15 12:00:00",
                "reject_reason": "证据不足",
            },
        ]

        text = regear._regear_status_text(rows)

        self.assertIn("已发放", text)
        self.assertIn("等额银币", text)
        self.assertIn("2026-06-15 19:00:00 北京时间", text)
        self.assertIn("已拒绝", text)
        self.assertIn("证据不足", text)
        self.assertIn("2026-06-15 20:00:00 北京时间", text)

    def test_regear_notice_card_labels_database_times_as_beijing(self):
        row = {
            "id": 123,
            "kook_user_id": "user-1",
            "event_id": "event-1",
            "est_value": 1000,
            "status": "rejected",
            "created_at": "2026-06-15 09:00:00",
            "reviewed_at": "2026-06-15 10:16:51",
            "reviewed_by": "admin",
            "reject_reason": "非补装范围",
        }

        text = card_text(regear_notice_card(row))

        self.assertIn("申请号：`#123`", text)
        self.assertIn("申请时间：`2026-06-15 17:00:00 北京时间`", text)
        self.assertIn("审核时间：`2026-06-15 18:16:51 北京时间`", text)
        self.assertNotIn("2026-06-15 10:16:51。", text)

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


class FakeBroadcastGameInfo:
    def __init__(self, events):
        self.events_data = events

    async def events(self, limit=51, offset=0):
        return self.events_data if offset == 0 else []

    async def guild_members(self, guild_id):
        return []


class FakeBroadcastMarket:
    def __init__(self, *, loss_total: int):
        self.loss_total = loss_total

    async def history(self, items, locations=None, qualities=None, time_scale=24):
        return [
            {
                "item_id": "T8_MAIN_SPEAR_KEEPER@1",
                "quality": 4,
                "location": "Caerleon",
                "data": [{"avg_price": self.loss_total}],
            }
        ]

    async def prices(self, items, locations=None, qualities=None):
        return []


class FakeAIService:
    def __init__(self, text):
        self.text = text
        self.regear_calls = []

    async def explain_regear(self, facts):
        self.regear_calls.append(facts)
        return self.text


class FakeUser:
    def __init__(self, roles, user_id="user"):
        self.id = user_id
        self.roles = roles


class FakeRole:
    def __init__(self, role_id, permissions=0):
        self.id = role_id
        self.name = f"role-{role_id}"
        self.permissions = permissions


class FakeGuild:
    def __init__(self, user):
        self.user = user
        self.master_id = "owner"
        self.granted_roles = []

    async def load(self):
        return None

    async def fetch_roles(self):
        return [FakeRole("reviewer")]

    async def fetch_user(self, user_id):
        self.user.id = user_id
        return self.user

    async def grant_role(self, user_id, role_id):
        self.granted_roles.append((user_id, role_id))


class FakeClient:
    def __init__(self, channels, guild):
        self.channels = channels
        self.guild = guild
        self.gate = FakeGate()

    async def fetch_guild(self, guild_id):
        return self.guild

    async def fetch_public_channel(self, channel_id):
        return self.channels[str(channel_id)]


class FakeBot:
    def __init__(self, channels, guild):
        self.client = FakeClient(channels, guild)


class FakeScheduledBot:
    def __init__(self, channels):
        self.client = FakeClient(channels, FakeGuild(FakeUser([])))
        self.task = FakeTaskRegistry()


class FakeTaskRegistry:
    def __init__(self):
        self.interval_tasks = {}
        self.cron_tasks = {}

    def add_interval(self, **kwargs):
        def decorate(fn):
            self.interval_tasks[fn.__name__] = fn
            return fn

        return decorate

    def add_cron(self, **kwargs):
        def decorate(fn):
            self.cron_tasks[fn.__name__] = fn
            return fn

        return decorate


class FakeGate:
    def __init__(self):
        self.requests = []

    async def exec_req(self, req):
        self.requests.append(req)
        return {}


class FakeChannel:
    def __init__(self, channel_id):
        self.id = channel_id
        self.messages = []

    async def send(self, message):
        self.messages.append(message)
        return {"msg_id": f"msg-{self.id}-{len(self.messages)}"}


def sample_regear_event(event_id="event-1"):
    return {
        "EventId": event_id,
        "TimeStamp": "2026-06-14T10:00:00",
        "TotalVictimKillFame": 99000,
        "numberOfParticipants": 3,
        "Victim": {
            "AverageItemPower": 1200,
            "Equipment": {
                "MainHand": {"Type": "T8_MAIN_SPEAR_KEEPER@1", "Quality": 4},
                "OffHand": {"Type": "T6_OFF_DEMONSKULL_HELL@3", "Quality": 4},
            },
        },
        "Killer": {"Name": "killer", "GuildName": "enemy"},
    }


def _broadcast_event(
    event_id="event-1",
    *,
    fame: int,
    killer_guild_id: str = "enemy",
    victim_guild_id: str = "enemy",
):
    return {
        "EventId": event_id,
        "TimeStamp": "2026-06-14T10:00:00",
        "TotalVictimKillFame": fame,
        "Killer": {
            "Name": "killer",
            "GuildId": killer_guild_id,
            "GuildName": "ours" if killer_guild_id == "guild" else "enemy",
        },
        "Victim": {
            "Name": "victim",
            "GuildId": victim_guild_id,
            "GuildName": "ours" if victim_guild_id == "guild" else "enemy",
            "Equipment": {
                "MainHand": {"Type": "T8_MAIN_SPEAR_KEEPER@1", "Quality": 4}
            },
        },
    }
