import os
import tempfile
import unittest
from datetime import date

from bot import config
from bot.ai.client import AIClient, AIClientConfig
from bot.ai.context import (
    battle_report_context,
    battles_context,
    binding_status_context,
    guild_config_context,
    player_recent_activity_context,
    regear_explain_context,
    regear_status_context,
)
from bot.ai.router import AIRouter
from bot.ai.service import AIService
from bot.commands import ai as ai_commands
from bot.store import repo
from bot.store.db import init_db


class FakeAIClient:
    def __init__(self, text="AI 说明"):
        self.text = text
        self.calls = []

    async def complete(self, messages, *, max_tokens=None):
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        return self.text


class FakeGameInfo:
    async def player(self, player_id):
        return {
            "Id": player_id,
            "Name": "Latano",
            "GuildName": "Mika",
            "KillFame": 123456,
            "DeathFame": 654321,
            "FameRatio": 1.2,
        }

    async def player_kills(self, player_id):
        return [
            {
                "EventId": "kill-1",
                "TimeStamp": "2026-06-14T10:00:00",
                "TotalVictimKillFame": 300000,
                "Victim": {"Name": "Enemy", "GuildName": "Bad", "AverageItemPower": 1300},
            }
        ]

    async def player_deaths(self, player_id):
        return [
            {
                "EventId": "death-1",
                "TimeStamp": "2026-06-14T11:00:00",
                "TotalVictimKillFame": 500000,
                "Killer": {"Name": "Killer", "GuildName": "Bad", "AverageItemPower": 1400},
                "Victim": {"Name": "Latano", "GuildName": "Mika", "AverageItemPower": 1200},
            }
        ]


class AIClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_ai_client_reads_openai_compatible_chat_completion(self):
        requests = []

        async def transport_handler(request):
            requests.append(request)
            return httpx_response(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "战报摘要",
                            }
                        }
                    ]
                }
            )

        client = AIClient(
            AIClientConfig(
                base_url="https://api.longcat.chat/openai",
                api_key="test-key",
                model="longcat-test",
                timeout=1.0,
                max_output_tokens=120,
            ),
            transport=transport_handler,
        )

        try:
            text = await client.complete([{"role": "user", "content": "总结"}])
        finally:
            await client.aclose()

        self.assertEqual(text, "战报摘要")
        self.assertEqual(requests[0].url.path, "/openai/v1/chat/completions")
        self.assertEqual(requests[0].headers["authorization"], "Bearer test-key")
        self.assertIn(b"longcat-test", requests[0].content)


class AIServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_service_returns_empty_without_calling_client(self):
        client = FakeAIClient()
        service = AIService(client, enabled=False)

        text = await service.guide_command("怎么绑定")

        self.assertEqual(text, "")
        self.assertEqual(client.calls, [])

    async def test_guide_command_uses_short_safe_prompt(self):
        client = FakeAIClient("先让管理员 /绑定公会，再由成员 /绑定 角色名。")
        service = AIService(client, enabled=True)

        text = await service.guide_command("我怎么绑定角色")

        self.assertIn("/绑定", text)
        self.assertEqual(client.calls[0]["max_tokens"], 300)
        prompt = "\n".join(m["content"] for m in client.calls[0]["messages"])
        self.assertIn("只回答 KOOK 机器人命令引导", prompt)
        self.assertIn("/绑定 <角色名> [自定义昵称]", prompt)
        self.assertIn("不要说 /设置 可以查看绑定状态", prompt)
        self.assertIn("不能批准", prompt)

    async def test_explain_regear_uses_structured_context_only(self):
        client = FakeAIClient("这单补装金额只计算穿戴装备，背包物品仅展示损失。")
        service = AIService(client, enabled=True)

        text = await service.explain_regear(
            {
                "request": {"id": 7, "status": "pending", "est_value": 123456},
                "event": {"EventId": "event-1", "TimeStamp": "2026-06-14T10:00:00"},
                "valuation": {
                    "equipment_total": 123456,
                    "inventory_total": 999999,
                    "loss_total": 1123455,
                    "missing_items": ["T8_FAKE"],
                },
            }
        )

        self.assertIn("补装金额", text)
        prompt = "\n".join(m["content"] for m in client.calls[0]["messages"])
        self.assertIn("JSON 事实包", prompt)
        self.assertIn("不得修改金额", prompt)
        self.assertNotIn("KOOK_TOKEN", prompt)

    async def test_all_ai_prompts_require_time_basis_labels(self):
        client = FakeAIClient("摘要")
        service = AIService(client, enabled=True)

        await service.summarize_battles(
            "Mika",
            [{"id": 1, "startTime": "2026-06-14T10:00:00"}],
        )

        prompt = "\n".join(m["content"] for m in client.calls[0]["messages"])
        self.assertIn("凡是回复里出现时间", prompt)
        self.assertIn("服务器/API 时间 UTC", prompt)
        self.assertIn("北京时间 UTC+8", prompt)
        self.assertIn("不要输出未标注的时间", prompt)

    async def test_summarize_battle_report_uses_structured_fact_pack(self):
        client = FakeAIClient("本会参战 3 人，Bob 阵亡压力较高。")
        service = AIService(client, enabled=True)

        text = await service.summarize_battle_report(
            {
                "battle_id": "123",
                "battle_url": "https://east.albionbb.com/battles/123",
                "guild_name": "Mika",
                "start_time": "2026-06-14T10:00:00",
                "total_players": 6,
                "total_kills": 8,
                "total_fame": 1234567,
                "guild_players": 3,
                "guild_kill_fame": 32000,
                "guild_row": {"kills": 4, "deaths": 3},
                "top_guilds": [{"name": "Mika", "players": 3, "kills": 4, "deaths": 3}],
                "top_alliances": [{"name": "5I7", "players": 3, "kills": 4, "deaths": 3}],
                "player_highlights": {"most_deaths": {"name": "Bob", "deaths": 2}},
            }
        )

        self.assertIn("本会参战", text)
        self.assertEqual(client.calls[0]["max_tokens"], 360)
        prompt = "\n".join(m["content"] for m in client.calls[0]["messages"])
        self.assertIn("battle_report_summary", prompt)
        self.assertIn("不要编造地图、战术", prompt)

    async def test_service_blocks_unsafe_action_claims_and_redacts_secrets(self):
        client = FakeAIClient("已批准 #1，KOOK_TOKEN=secret，Bearer abc123，ak_2Ia6kF9TM5q36dQ7G27382BO2cl7B")
        service = AIService(client, enabled=True)

        text = await service.answer_readonly_query("查补装", {"schema_version": "ai.v1"})

        self.assertIn("只读说明", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("abc123", text)
        self.assertNotIn("ak_2Ia6", text)

    async def test_service_allows_readonly_status_wording(self):
        client = FakeAIClient("申请 #1 状态为已批准（待发放），请线下发放后由审核员点按钮。")
        service = AIService(client, enabled=True)

        text = await service.answer_readonly_query("查补装", {"schema_version": "ai.v1"})

        self.assertIn("状态为已批准", text)
        self.assertNotIn("只读说明", text)


class AIRouterTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "bot.db")
        init_db()

    def tearDown(self):
        config.DB_PATH = self.old_db
        self.tmp.cleanup()

    async def test_router_handles_regear_status_with_readonly_tool(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        rid = repo.create_regear("guild", "user-1", "player-1", "event-1", 1000)
        service = AIService(FakeAIClient("查询结果：#1 待审批，金额 1,000 银。"), enabled=True)
        router = AIRouter(service)

        text = await router.answer("guild", "user-1", "查一下我的补装状态")

        self.assertIn("查询结果", text)
        self.assertIn(str(rid), text)

    async def test_router_limits_regear_status_to_own_rows_for_regular_user(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        own_id = repo.create_regear("guild", "user-1", "player-1", "event-1", 1000)
        other_id = repo.create_regear("guild", "user-2", "player-2", "event-2", 2000)
        service = AIService(FakeAIClient(), enabled=False)
        router = AIRouter(service)

        text = await router.answer("guild", "user-1", "查一下待发放补装申请")

        self.assertIn(f"#{own_id}", text)
        self.assertNotIn(f"#{other_id}", text)

    async def test_router_allows_regear_manager_to_read_guild_rows(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        own_id = repo.create_regear("guild", "user-1", "player-1", "event-1", 1000)
        other_id = repo.create_regear("guild", "user-2", "player-2", "event-2", 2000)
        service = AIService(FakeAIClient(), enabled=False)
        router = AIRouter(service)

        text = await router.answer(
            "guild",
            "reviewer",
            "查一下待发放补装申请",
            can_manage_regear=True,
        )

        self.assertIn(f"#{own_id}", text)
        self.assertIn(f"#{other_id}", text)

    async def test_router_rejects_mutating_intent(self):
        service = AIService(FakeAIClient("不应调用"), enabled=True)
        router = AIRouter(service)

        text = await router.answer("guild", "admin", "帮我通过 1 号补装并发身份组")

        self.assertIn("不能执行审批", text)
        self.assertEqual(service.client.calls, [])

    async def test_router_guides_non_whitelisted_questions(self):
        service = AIService(FakeAIClient("成员可用 /绑定 <角色名> [自定义昵称]。"), enabled=True)
        router = AIRouter(service)

        text = await router.answer("guild", "user-1", "我怎么绑定角色")

        self.assertIn("/绑定 <角色名> [自定义昵称]", text)
        prompt = "\n".join(m["content"] for m in service.client.calls[0]["messages"])
        self.assertIn("只回答 KOOK 机器人命令引导", prompt)

    async def test_router_answers_binding_status_from_whitelisted_fact_pack(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_player_binding("user-1", "guild", "player-1", "Latano")
        service = AIService(FakeAIClient("你已绑定 Latano。"), enabled=True)
        router = AIRouter(service)

        text = await router.answer("guild", "user-1", "我的绑定状态")

        self.assertIn("Latano", text)
        prompt = "\n".join(m["content"] for m in service.client.calls[0]["messages"])
        self.assertIn('"tool":"binding_status"', prompt)
        self.assertIn('"schema_version"', prompt)
        self.assertIn("Latano", prompt)
        self.assertNotIn("kook_user_id", prompt)

    async def test_router_limits_guild_config_summary_to_admins(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "member_role_id", "role-1")
        repo.set_setting("guild", "approval_channel_id", "approval")
        service = AIService(FakeAIClient("配置概况：已设置会员身份组和审批频道。"), enabled=True)
        router = AIRouter(service)

        denied = await router.answer("guild", "user-1", "频道配置概况", can_manage_guild=False)
        allowed = await router.answer("guild", "admin", "频道配置概况", can_manage_guild=True)

        self.assertIn("只有管理员", denied)
        self.assertIn("会员身份组", allowed)
        self.assertEqual(len(service.client.calls), 1)
        prompt = "\n".join(m["content"] for m in service.client.calls[0]["messages"])
        self.assertIn('"tool":"guild_config"', prompt)
        self.assertIn('"approval_channel_id":"approval"', prompt)

    async def test_router_answers_recent_activity_for_bound_player(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_player_binding("user-1", "guild", "player-1", "Latano")
        service = AIService(FakeAIClient("最近阵亡 1 次，时间已标注。"), enabled=True)
        router = AIRouter(service, gameinfo=FakeGameInfo())

        text = await router.answer("guild", "user-1", "我的最近死亡")

        self.assertIn("最近阵亡", text)
        prompt = "\n".join(m["content"] for m in service.client.calls[0]["messages"])
        self.assertIn('"tool":"player_recent_activity"', prompt)
        self.assertIn("death-1", prompt)
        self.assertIn("服务器/API 时间", prompt)

    async def test_router_treats_regear_queue_summary_as_readonly_query(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        own_id = repo.create_regear("guild", "user-1", "player-1", "event-1", 1000)
        other_id = repo.create_regear("guild", "user-2", "player-2", "event-2", 2000)
        service = AIService(FakeAIClient(), enabled=False)
        router = AIRouter(service)

        text = await router.answer(
            "guild",
            "reviewer",
            "补装队列概况",
            can_manage_regear=True,
        )

        self.assertIn(f"#{own_id}", text)
        self.assertIn(f"#{other_id}", text)


class AIContextTest(unittest.TestCase):
    def test_core_contexts_include_schema_version(self):
        self.assertIn(
            "schema_version",
            regear_status_context([], own_only=True),
        )
        self.assertIn("schema_version", battles_context("Mika", []))

    def test_regear_context_extracts_safe_summary(self):
        context = regear_explain_context(
            {"id": 3, "status": "pending", "est_value": 2000, "kook_user_id": "user"},
            {"EventId": "event-1", "TimeStamp": "2026-06-14T10:00:00"},
            {
                "total": 2000,
                "items": [
                    {"slot": "MainHand", "type": "T8_MAIN_SPEAR_KEEPER@1", "value": 2000},
                    {"slot": None, "type": "T8_BAG", "value": 5000},
                    {"slot": "OffHand", "type": "T8_FAKE", "value": 0},
                ],
            },
        )

        self.assertEqual(context["request"]["id"], 3)
        self.assertIn("schema_version", context)
        self.assertEqual(context["valuation"]["equipment_total"], 2000)
        self.assertEqual(context["valuation"]["inventory_total"], 5000)
        self.assertIn("T8_FAKE", context["valuation"]["missing_items"])
        self.assertNotIn("kook_user_id", context["request"])

    def test_regear_status_context_includes_review_outcome_details(self):
        context = regear_status_context(
            [
                {
                    "id": 1,
                    "status": "rejected",
                    "est_value": 2000,
                    "reject_reason": "证据不足",
                    "payout_method": None,
                    "payout_note": None,
                },
                {
                    "id": 2,
                    "status": "paid",
                    "est_value": 3000,
                    "reject_reason": None,
                    "payout_method": "silver",
                    "payout_note": "等额银币",
                },
            ],
            own_only=True,
        )

        self.assertEqual(context["requests"][0]["reject_reason"], "证据不足")
        self.assertEqual(context["requests"][1]["payout_method"], "silver")
        self.assertEqual(context["requests"][1]["payout_note"], "等额银币")

    def test_regear_context_labels_api_event_time(self):
        context = regear_explain_context(
            {"id": 3, "status": "pending", "est_value": 2000},
            {"EventId": "event-1", "TimeStamp": "2026-06-14T10:00:00"},
            {"total": 2000, "items": []},
        )

        event_time = context["event"]["time"]
        self.assertEqual(
            event_time["server_time_utc"],
            "2026-06-14 10:00 UTC（服务器/API 时间）",
        )
        self.assertEqual(
            event_time["beijing_time_utc8"],
            "2026-06-14 18:00 UTC+8（北京时间）",
        )
        self.assertIn("服务器/API 时间 UTC", event_time["basis"])
        self.assertIn("北京时间 UTC+8", event_time["basis"])

    def test_battles_context_labels_battle_start_time(self):
        context = battles_context(
            "Mika",
            [{"id": 1, "startTime": "2026-06-14T10:00:00"}],
        )

        start_time = context["battles"][0]["start_time"]
        self.assertEqual(
            start_time["server_time_utc"],
            "2026-06-14 10:00 UTC（服务器/API 时间）",
        )
        self.assertEqual(
            start_time["beijing_time_utc8"],
            "2026-06-14 18:00 UTC+8（北京时间）",
        )

    def test_battle_report_date_arg_filters_beijing_night_window(self):
        target = ai_commands._parse_battle_report_date(
            ("6-15",), today=date(2026, 6, 16)
        )
        battles = ai_commands._filter_battle_report_battles(
            [
                {"id": "old-night", "startTime": "2026-06-14T13:31:00Z"},
                {"id": "target-evening", "startTime": "2026-06-15T15:27:29.938919200Z"},
                {"id": "target-after-midnight", "startTime": "2026-06-15T16:20:34Z"},
                {"id": "next-day", "startTime": "2026-06-16T10:00:00Z"},
            ],
            target,
        )

        self.assertEqual(
            [b["id"] for b in battles],
            ["target-evening", "target-after-midnight"],
        )

    def test_battle_report_context_is_safe_and_readonly(self):
        context = battle_report_context(
            {
                "battle_id": "123",
                "battle_url": "https://east.albionbb.com/battles/123",
                "guild_name": "Mika",
                "start_time": "2026-06-14T10:00:00",
                "total_players": 6,
                "total_kills": 8,
                "total_fame": 1234567,
                "guild_players": 3,
                "guild_kill_fame": 32000,
                "guild_row": {"kills": 4, "deaths": 3},
                "top_guilds": [{"name": "Mika", "players": 3, "kills": 4, "deaths": 3}],
                "top_alliances": [{"name": "5I7", "players": 3, "kills": 4, "deaths": 3}],
                "player_highlights": {"most_deaths": {"name": "Bob", "deaths": 2}},
            }
        )

        self.assertEqual(context["tool"], "battle_report_summary")
        self.assertEqual(context["guild"]["players"], 3)
        self.assertEqual(context["leaders"]["guilds"][0]["name"], "Mika")
        self.assertEqual(context["highlights"]["most_deaths"]["name"], "Bob")
        self.assertTrue(context["policy"]["readonly_summary_only"])

    def test_regear_status_context_labels_database_times(self):
        context = regear_status_context(
            [
                {
                    "id": 1,
                    "status": "pending",
                    "est_value": 2000,
                    "event_id": "event-1",
                    "created_at": "2026-06-14 10:00:00",
                    "reviewed_at": None,
                    "paid_at": None,
                }
            ],
            own_only=True,
        )

        created_time = context["requests"][0]["created_time"]
        self.assertEqual(
            created_time["server_time_utc"],
            "2026-06-14 10:00 UTC（数据库/服务器时间）",
        )
        self.assertEqual(
            created_time["beijing_time_utc8"],
            "2026-06-14 18:00 UTC+8（北京时间）",
        )
        self.assertNotIn("created_at", context["requests"][0])

    def test_binding_status_context_keeps_only_safe_user_facts(self):
        context = binding_status_context(
            {"albion_guild_name": "Mika"},
            {
                "kook_user_id": "user-1",
                "albion_player_name": "Latano",
                "custom_nickname": "lt",
                "status": "verified",
            },
            None,
        )

        self.assertEqual(context["tool"], "binding_status")
        self.assertEqual(context["player_binding"]["albion_player_name"], "Latano")
        self.assertEqual(context["player_binding"]["custom_nickname"], "lt")
        self.assertNotIn("kook_user_id", context["player_binding"])

    def test_guild_config_context_reports_safe_configuration_summary(self):
        context = guild_config_context(
            {
                "albion_guild_name": "Mika",
                "member_role_id": "role-1",
                "approval_channel_id": "approval",
                "broadcast_channel_id": "",
                "kill_broadcast_channel_id": None,
                "death_broadcast_channel_id": None,
                "battle_report_channel_id": "battle-report",
                "battle_report_min_guild_players": 25,
                "member_change_channel_id": None,
                "regear_channel_id": "regear",
                "regear_apply_channel_id": "regear-apply",
                "regear_review_channel_id": "regear-review",
                "regear_payout_channel_id": "regear-payout",
                "regear_notify_channel_id": "regear-notify",
                "regear_reviewer_role_ids": "role-a,role-b",
                "trusted_role_ids": "",
                "kill_fame_threshold": 100000,
                "created_by": "admin-user",
            }
        )

        self.assertEqual(context["tool"], "guild_config")
        self.assertTrue(context["settings"]["member_role_id"]["configured"])
        self.assertEqual(context["settings"]["regear_apply_channel_id"], "regear-apply")
        self.assertEqual(context["settings"]["regear_review_channel_id"], "regear-review")
        self.assertEqual(context["settings"]["regear_payout_channel_id"], "regear-payout")
        self.assertEqual(context["settings"]["regear_notify_channel_id"], "regear-notify")
        self.assertEqual(context["settings"]["battle_report_channel_id"], "battle-report")
        self.assertEqual(context["settings"]["battle_report_min_guild_players"], 25)
        self.assertEqual(context["settings"]["regear_reviewer_role_count"], 2)
        self.assertNotIn("created_by", context)

    def test_player_recent_activity_context_labels_event_times(self):
        context = player_recent_activity_context(
            {"Name": "Latano", "GuildName": "Mika", "KillFame": 1, "DeathFame": 2},
            [],
            [
                {
                    "EventId": "death-1",
                    "TimeStamp": "2026-06-14T11:00:00",
                    "TotalVictimKillFame": 500000,
                    "Killer": {"Name": "Killer", "GuildName": "Bad"},
                }
            ],
        )

        self.assertEqual(context["tool"], "player_recent_activity")
        self.assertEqual(context["recent_deaths"][0]["time"]["server_time_utc"], "2026-06-14 11:00 UTC（服务器/API 时间）")
        self.assertNotIn("kook_user_id", str(context))


def httpx_response(payload):
    import json

    import httpx

    request = httpx.Request("POST", "https://api.longcat.chat/openai/v1/chat/completions")
    return httpx.Response(200, json=payload, request=request)
