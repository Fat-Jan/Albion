import unittest
from types import SimpleNamespace
from unittest.mock import patch

from khl import EventTypes

from bot import region_scope
from bot.commands import admin
from scripts import ensure_region_channels


class RegionScopeTest(unittest.IsolatedAsyncioTestCase):
    def test_eu_default_prefixes_regear_channel_names(self):
        self.assertEqual(region_scope.region_code(), "eu")
        self.assertEqual(region_scope.scoped_name("📥补装申请"), "eu-📥补装申请")

    def test_region_helpers_accept_explicit_region(self):
        self.assertEqual(region_scope.scoped_name("📥补装申请", region="asia"), "asia-📥补装申请")
        self.assertTrue(
            region_scope.channel_name_matches_region("asia-📥补装申请", region="asia")
        )
        self.assertFalse(
            region_scope.channel_name_matches_region("eu-📥补装申请", region="asia")
        )

    def test_region_scope_no_longer_infers_region_from_config_urls(self):
        self.assertFalse(hasattr(region_scope, "_infer_region_from_config"))

    def test_channel_name_must_match_current_region_prefix(self):
        self.assertTrue(region_scope.channel_name_matches_region("eu-📥补装申请"))
        self.assertFalse(region_scope.channel_name_matches_region("asia-📥补装申请"))
        self.assertFalse(region_scope.channel_name_matches_region("📥补装申请"))

    def test_process_message_only_in_region_channel(self):
        msg = SimpleNamespace(
            ctx=SimpleNamespace(channel=SimpleNamespace(name="asia-📥补装申请"))
        )

        self.assertFalse(region_scope.should_process_message(msg))

    def test_bootstrap_commands_do_not_reply_in_unscoped_channels(self):
        msg = SimpleNamespace(ctx=SimpleNamespace(channel=SimpleNamespace(name="随便哪个频道")))

        self.assertFalse(region_scope.should_process_message(msg, allow_bootstrap=True))

    def test_bootstrap_does_not_allow_other_region_channels(self):
        msg = SimpleNamespace(ctx=SimpleNamespace(channel=SimpleNamespace(name="asia-📥补装申请")))

        self.assertFalse(region_scope.should_process_message(msg, allow_bootstrap=True))

    def test_configured_channel_id_accepts_plain_name_but_rejects_other_region_prefix(self):
        binding = {"approval_channel_id": "111"}

        self.assertTrue(
            region_scope.configured_channel_matches_region(
                binding, "111", ("approval_channel_id",), SimpleNamespace()
            )
        )
        self.assertTrue(
            region_scope.configured_channel_matches_region(
                binding,
                "111",
                ("approval_channel_id",),
                SimpleNamespace(name="审批频道"),
            )
        )
        self.assertTrue(
            region_scope.configured_channel_matches_region(
                binding,
                "111",
                ("approval_channel_id",),
                SimpleNamespace(name="eu-审批频道"),
            )
        )
        self.assertFalse(
            region_scope.configured_channel_matches_region(
                binding,
                "111",
                ("approval_channel_id",),
                SimpleNamespace(name="asia-审批频道"),
            )
        )

    def test_process_message_allows_configured_channel_id_without_prefix(self):
        msg = SimpleNamespace(
            ctx=SimpleNamespace(
                guild=SimpleNamespace(id="guild-1"),
                channel=SimpleNamespace(id="111", name="审批频道"),
            )
        )

        with patch.object(
            region_scope.repo,
            "get_guild_binding",
            return_value={"approval_channel_id": "111"},
        ) as get_binding:
            self.assertTrue(region_scope.should_process_message(msg, region="eu"))

        get_binding.assert_called_once_with("guild-1", "eu")

    def test_process_message_rejects_configured_id_with_other_region_prefix(self):
        msg = SimpleNamespace(
            ctx=SimpleNamespace(
                guild=SimpleNamespace(id="guild-1"),
                channel=SimpleNamespace(id="111", name="asia-审批频道"),
            )
        )

        with patch.object(
            region_scope.repo,
            "get_guild_binding",
            return_value={"approval_channel_id": "111"},
        ):
            self.assertFalse(region_scope.should_process_message(msg, region="eu"))

    def test_new_channel_cutoff_excludes_channels_before_june_2026(self):
        old_channel = SimpleNamespace(
            id="old",
            name="eu-旧频道",
            created_at="2026-05-31T23:59:59Z",
        )
        new_channel = SimpleNamespace(
            id="new",
            name="eu-新频道",
            created_at="2026-06-01T00:00:00Z",
        )

        self.assertFalse(region_scope.is_channel_created_in_scope(old_channel))
        self.assertTrue(region_scope.is_channel_created_in_scope(new_channel))

    async def test_resolve_channel_only_accepts_current_region_prefix(self):
        guild = SimpleNamespace(
            fetch_channel_list=lambda: _async_value(
                [
                    SimpleNamespace(id="plain", name="📥补装申请"),
                    SimpleNamespace(id="222", name="asia-📥补装申请"),
                    SimpleNamespace(id="333", name="eu-📥补装申请"),
                ]
            )
        )

        self.assertEqual(await admin._resolve_channel(guild, "📥补装申请"), "333")
        self.assertIsNone(await admin._resolve_channel(guild, "asia-📥补装申请"))
        self.assertIsNone(await admin._resolve_channel(guild, "(chn)222(chn)"))
        self.assertEqual(await admin._resolve_channel(guild, "(chn)333(chn)"), "333")

    async def test_initialize_channels_creates_scoped_operations_and_regear_groups(self):
        existing = [FakeChannel("legacy-approval", "✅绑定审批")]
        guild = FakeAdminGuild(existing)
        binding = {"member_role_id": "member", "regear_reviewer_role_ids": "reviewer"}

        ops_category, ops_channels = await admin._create_operations_center(guild)
        regear_category, regear_channels, warnings = await admin._create_regear_center(
            FakeAdminBot(), guild, binding
        )

        self.assertEqual(ops_category.name, "eu-📡运营中心")
        self.assertEqual(regear_category.name, "eu-🛡️补装中心")
        self.assertEqual(
            {field: channel.name for field, channel in ops_channels.items()},
            {
                "approval_channel_id": "eu-✅绑定审批",
                "member_change_channel_id": "eu-📢成员变动",
                "kill_broadcast_channel_id": "eu-⚔️击杀播报",
                "death_broadcast_channel_id": "eu-💀阵亡播报",
                "battle_report_channel_id": "eu-🗺️战报推送",
            },
        )
        self.assertEqual(
            {field: channel.name for field, channel in regear_channels.items()},
            {
                "regear_apply_channel_id": "eu-📥补装申请",
                "regear_review_channel_id": "eu-🔍补装审核",
                "regear_payout_channel_id": "eu-💰补装发放",
                "regear_notify_channel_id": "eu-📣补装通知",
            },
        )
        self.assertEqual(warnings, [])
        self.assertNotIn("legacy-approval", [channel.id for channel in ops_channels.values()])

    async def test_admin_initializers_reuse_categories_from_category_list(self):
        guild = FakeSplitListGuild(
            categories=[
                FakeChannel("ops-category", "eu-📡运营中心"),
                FakeChannel("regear-category", "eu-🛡️补装中心"),
            ],
            channels=[],
        )

        ops_category, _ = await admin._create_operations_center(guild)
        regear_category, _ = await admin._create_regear_center_channels(guild)

        self.assertEqual(ops_category.id, "ops-category")
        self.assertEqual(regear_category.id, "regear-category")
        self.assertEqual(guild.created_categories, [])

    async def test_self_joined_guild_creates_scoped_layout_without_binding_settings(self):
        guild = FakeAdminGuild([])
        bot = FakeCommandBot(guild)
        admin.register(bot, SimpleNamespace())
        handler = bot.handler_for(EventTypes.SELF_JOINED_GUILD)

        with patch.object(admin.repo, "set_setting", side_effect=AssertionError("must not write settings")):
            await handler(bot, SimpleNamespace(body={"guild_id": "guild-1"}))

        self.assertEqual(bot.client.fetched_guild_ids, ["guild-1"])
        self.assertEqual(
            [channel.name for channel in guild.created_categories],
            ["eu-📡运营中心", "eu-🛡️补装中心"],
        )
        self.assertEqual(
            [channel.name for channel in guild.created_text_channels],
            [
                "eu-✅绑定审批",
                "eu-📢成员变动",
                "eu-⚔️击杀播报",
                "eu-💀阵亡播报",
                "eu-🗺️战报推送",
                "eu-📥补装申请",
                "eu-🔍补装审核",
                "eu-💰补装发放",
                "eu-📣补装通知",
            ],
        )

    def test_ensure_layout_ignores_plain_and_other_region_channels(self):
        layout = ensure_region_channels.plan_region_layout(
            [
                FakeChannel("plain", "📥补装申请"),
                FakeChannel("asia", "asia-📥补装申请"),
                FakeChannel("eu", "eu-📥补装申请"),
            ],
            {"regear_apply_channel_id": "📥补装申请"},
        )

        self.assertEqual(layout["regear_apply_channel_id"].channel.id, "eu")

    def test_ensure_layout_marks_missing_region_channel_for_creation(self):
        layout = ensure_region_channels.plan_region_layout(
            [
                FakeChannel("plain", "📥补装申请"),
                FakeChannel("asia", "asia-📥补装申请"),
            ],
            {"regear_apply_channel_id": "📥补装申请"},
        )

        self.assertIsNone(layout["regear_apply_channel_id"].channel)
        self.assertEqual(layout["regear_apply_channel_id"].name, "eu-📥补装申请")

    async def test_ensure_region_layout_reuses_existing_categories(self):
        guild = FakeEnsureGuild(
            categories=[
                FakeChannel("ops-category", "eu-📡运营中心"),
                FakeChannel("regear-category", "eu-🛡️补装中心"),
            ],
            channels=[],
        )

        categories, channels = await ensure_region_channels.ensure_region_layout(guild)

        self.assertEqual(categories["operations"].id, "ops-category")
        self.assertEqual(categories["regear"].id, "regear-category")
        self.assertEqual(guild.created_categories, [])
        self.assertEqual(
            {field: channel.name for field, channel in channels.items()},
            {
                "approval_channel_id": "eu-✅绑定审批",
                "member_change_channel_id": "eu-📢成员变动",
                "kill_broadcast_channel_id": "eu-⚔️击杀播报",
                "death_broadcast_channel_id": "eu-💀阵亡播报",
                "battle_report_channel_id": "eu-🗺️战报推送",
                "regear_apply_channel_id": "eu-📥补装申请",
                "regear_review_channel_id": "eu-🔍补装审核",
                "regear_payout_channel_id": "eu-💰补装发放",
                "regear_notify_channel_id": "eu-📣补装通知",
            },
        )


async def _async_value(value):
    return value


class FakeAdminBot:
    client = SimpleNamespace(fetch_me=lambda: _async_value(SimpleNamespace(username="bot", nickname="bot")))


class FakeCommandBot(FakeAdminBot):
    def __init__(self, guild):
        self.client = FakeAdminClient(guild)
        self.commands = {}
        self.events = []

    def command(self, name):
        def decorate(fn):
            self.commands[name] = fn
            return fn

        return decorate

    def on_event(self, event_type):
        def decorate(fn):
            self.events.append((event_type, fn))
            return fn

        return decorate

    def handler_for(self, event_type):
        for registered, handler in self.events:
            if registered == event_type:
                return handler
        raise AssertionError(f"handler not registered: {event_type}")


class FakeAdminClient:
    def __init__(self, guild):
        self.guild = guild
        self.fetched_guild_ids = []

    async def fetch_guild(self, guild_id):
        self.fetched_guild_ids.append(guild_id)
        return self.guild

    async def fetch_me(self):
        return SimpleNamespace(username="bot", nickname="bot")


class FakeAdminRole:
    id = "bot-role"
    name = "bot"
    type = 1
    permissions = 0


class FakeChannel:
    def __init__(self, channel_id, name, created_at="2026-06-10T00:00:00Z"):
        self.id = channel_id
        self.name = name
        self.created_at = created_at
        self.permissions = []

    async def create_role_permission(self, role_id):
        self.permissions.append(("create", role_id))

    async def update_role_permission(self, role_id, *, allow=0, deny=0):
        self.permissions.append(("update", role_id, allow, deny))


class FakeAdminGuild:
    def __init__(self, channels):
        self.channels = list(channels)
        self.created_categories = []
        self.created_text_channels = []

    async def fetch_channel_list(self):
        return list(self.channels)

    async def fetch_roles(self):
        return [FakeAdminRole()]

    async def create_channel_category(self, name):
        channel = FakeChannel(f"category-{len(self.created_categories) + 1}", name)
        self.channels.append(channel)
        self.created_categories.append(channel)
        return channel

    async def create_text_channel(self, name, category):
        channel = FakeChannel(f"text-{len(self.created_text_channels) + 1}", name)
        channel.category = category
        self.channels.append(channel)
        self.created_text_channels.append(channel)
        return channel


class FakeEnsureGuild:
    def __init__(self, categories, channels):
        self.categories = list(categories)
        self.channels = list(channels)
        self.created_categories = []
        self.created_text_channels = []

    async def fetch_channel_category_list(self):
        return list(self.categories)

    async def fetch_channel_list(self):
        return list(self.channels)

    async def create_channel_category(self, name):
        channel = FakeChannel(f"category-{len(self.created_categories) + 1}", name)
        self.categories.append(channel)
        self.created_categories.append(channel)
        return channel

    async def create_text_channel(self, name, category):
        channel = FakeChannel(f"text-{len(self.created_text_channels) + 1}", name)
        channel.category = category
        self.channels.append(channel)
        self.created_text_channels.append(channel)
        return channel


class FakeSplitListGuild(FakeEnsureGuild):
    async def fetch_roles(self):
        return [FakeAdminRole()]


if __name__ == "__main__":
    unittest.main()
