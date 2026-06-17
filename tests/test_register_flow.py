import os
import sqlite3
import tempfile
import unittest

from bot import config
from bot.cards.register_cards import approval_card, binding_result_card
from bot.commands import register
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


class RegisterFlowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "bot.db")
        init_db()

    def tearDown(self):
        config.DB_PATH = self.old_db
        self.tmp.cleanup()

    def test_bind_approval_card_shows_request_id_and_pending_status(self):
        card = approval_card(
            12,
            "user-1",
            {"Name": "Latano", "GuildName": "Mika", "KillFame": 1000},
        )

        text = card_text(card)

        self.assertIn("申请号：`#12`", text)
        self.assertIn("当前状态：`待审批`", text)
        self.assertIn("(met)user-1(met)", text)

    def test_bind_result_card_shows_request_id(self):
        card = binding_result_card(
            {
                "id": 12,
                "kook_user_id": "user-1",
                "albion_player_name": "Latano",
                "status": "approved",
            }
        )

        text = card_text(card)

        self.assertIn("绑定申请 `#12` 已通过", text)
        self.assertIn("申请号：`#12`", text)

    def test_bind_args_accept_space_or_dash_custom_nickname(self):
        self.assertEqual(register._parse_bind_args(("BEISHENGS", "北笙")), ("BEISHENGS", "北笙"))
        self.assertEqual(register._parse_bind_args(("BEISHENGS", "-", "北笙")), ("BEISHENGS", "北笙"))
        self.assertEqual(register._parse_bind_args(("DT777",)), ("DT777", None))

    def test_bind_approval_card_shows_custom_nickname_target(self):
        card = approval_card(
            12,
            "user-1",
            {"Name": "BEISHENGS", "GuildName": "Mika", "KillFame": 1000},
            "北笙",
        )

        text = card_text(card)

        self.assertIn("KOOK 昵称：`BEISHENGS - 北笙`", text)

    def test_init_db_migrates_custom_nickname_columns(self):
        conn = sqlite3.connect(config.DB_PATH)
        try:
            conn.executescript(
                """
                DROP TABLE player_binding;
                DROP TABLE pending_approval;
                CREATE TABLE player_binding (
                  kook_user_id TEXT NOT NULL,
                  kook_guild_id TEXT NOT NULL,
                  albion_player_id TEXT NOT NULL,
                  albion_player_name TEXT NOT NULL,
                  status TEXT DEFAULT 'verified',
                  bound_at TEXT DEFAULT (datetime('now')),
                  PRIMARY KEY (kook_user_id, kook_guild_id)
                );
                CREATE TABLE pending_approval (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  kook_guild_id TEXT NOT NULL,
                  kook_user_id TEXT NOT NULL,
                  albion_player_id TEXT NOT NULL,
                  albion_player_name TEXT NOT NULL,
                  message_id TEXT,
                  status TEXT DEFAULT 'pending',
                  created_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

        init_db()

        repo.set_player_binding("user-1", "guild", "player-1", "BEISHENGS", "北笙")
        pid = repo.create_pending("guild", "user-2", "player-2", "DT777", "dt")
        self.assertEqual(repo.get_player_binding("user-1", "guild")["custom_nickname"], "北笙")
        self.assertEqual(repo.get_pending(pid)["custom_nickname"], "dt")

    def test_pending_approval_records_custom_nickname(self):
        pid = repo.create_pending("guild", "user-1", "player-1", "BEISHENGS", "北笙")

        pending = repo.get_pending(pid)

        self.assertEqual(pending["custom_nickname"], "北笙")

    async def test_finalize_bind_sets_game_name_dash_custom_nickname(self):
        guild = FakeGuild(FakeUser(["member-role"], user_id="user-1"))

        warnings = await register._finalize_bind(
            guild,
            "user-1",
            "member-role",
            "player-1",
            "BEISHENGS",
            "北笙",
        )

        binding = repo.get_player_binding("user-1", "guild")
        self.assertEqual(warnings, [])
        self.assertEqual(binding["albion_player_name"], "BEISHENGS")
        self.assertEqual(binding["custom_nickname"], "北笙")
        self.assertEqual(guild.nicknames, [("user-1", "BEISHENGS - 北笙")])

    async def test_bind_approval_notifies_member_change_channel(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "member_role_id", "member-role")
        repo.set_setting("guild", "approval_channel_id", "approval")
        repo.set_setting("guild", "member_change_channel_id", "member-change")
        pid = repo.create_pending("guild", "user-1", "player-1", "Latano")
        channels = {"approval": FakeChannel("approval"), "member-change": FakeChannel("member-change")}
        guild = FakeGuild(FakeUser(["admin-role"], user_id="admin"))
        bot = FakeBot(channels, guild)

        await register._handle_bind_review(
            bot,
            "approve_bind",
            {"pid": pid},
            "guild",
            "admin",
            channels["approval"],
        )

        self.assertEqual(repo.get_pending(pid)["status"], "approved")
        self.assertEqual(repo.get_player_binding("user-1", "guild")["albion_player_name"], "Latano")
        self.assertEqual(len(channels["member-change"].messages), 1)
        notice = card_text(channels["member-change"].messages[0])
        self.assertIn("绑定申请 `#1` 已通过", notice)
        self.assertIn("(met)user-1(met)", notice)
        self.assertIn("Latano", notice)
        self.assertIn("角色绑定已生效", notice)

    async def test_bind_rejection_notifies_member_change_channel_with_request_id(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "member_role_id", "member-role")
        repo.set_setting("guild", "approval_channel_id", "approval")
        repo.set_setting("guild", "member_change_channel_id", "member-change")
        pid = repo.create_pending("guild", "user-1", "player-1", "Latano")
        channels = {"approval": FakeChannel("approval"), "member-change": FakeChannel("member-change")}
        bot = FakeBot(channels, FakeGuild(FakeUser(["admin-role"], user_id="admin")))

        await register._handle_bind_review(
            bot,
            "reject_bind",
            {"pid": pid},
            "guild",
            "admin",
            channels["approval"],
        )

        self.assertEqual(repo.get_pending(pid)["status"], "rejected")
        self.assertIsNone(repo.get_player_binding("user-1", "guild"))
        self.assertEqual(len(channels["member-change"].messages), 1)
        notice = card_text(channels["member-change"].messages[0])
        self.assertIn("绑定申请 `#1` 已拒绝", notice)
        self.assertIn("(met)user-1(met)", notice)
        self.assertIn("Latano", notice)

    async def test_bind_review_updates_original_approval_card_status(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "member_role_id", "member-role")
        repo.set_setting("guild", "approval_channel_id", "approval")
        repo.set_setting("guild", "member_change_channel_id", "member-change")
        pid = repo.create_pending("guild", "user-1", "player-1", "Latano")
        repo.set_pending_message(pid, "msg-bind-1")
        channels = {"approval": FakeChannel("approval"), "member-change": FakeChannel("member-change")}
        bot = FakeBot(channels, FakeGuild(FakeUser(["admin-role"], user_id="admin")))

        await register._handle_bind_review(
            bot,
            "reject_bind",
            {"pid": pid},
            "guild",
            "admin",
            channels["approval"],
        )

        updates = [req for req in bot.client.gate.requests if req.route == "message/update"]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].params["json"]["msg_id"], "msg-bind-1")
        content = updates[0].params["json"]["content"]
        self.assertIn("绑定申请 `#1` 已拒绝", content)
        self.assertIn("当前状态：`已拒绝`", content)

    async def test_bind_notification_falls_back_to_approval_channel(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "member_role_id", "member-role")
        repo.set_setting("guild", "approval_channel_id", "approval")
        pid = repo.create_pending("guild", "user-1", "player-1", "Latano")
        channels = {"approval": FakeChannel("approval")}
        bot = FakeBot(channels, FakeGuild(FakeUser(["admin-role"], user_id="admin")))

        await register._handle_bind_review(
            bot,
            "approve_bind",
            {"pid": pid},
            "guild",
            "admin",
            channels["approval"],
        )

        self.assertTrue(
            any("绑定申请 `#1` 已通过" in card_text(msg) for msg in channels["approval"].messages)
        )

    async def test_bind_notification_skips_non_region_configured_channel(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "member_role_id", "member-role")
        repo.set_setting("guild", "approval_channel_id", "approval")
        repo.set_setting("guild", "member_change_channel_id", "member-change")
        pid = repo.create_pending("guild", "user-1", "player-1", "Latano")
        channels = {
            "approval": FakeChannel("approval", name="eu-✅绑定审批"),
            "member-change": FakeChannel("member-change", name="📢成员变动"),
        }
        bot = FakeBot(channels, FakeGuild(FakeUser(["admin-role"], user_id="admin")))

        await register._handle_bind_review(
            bot,
            "approve_bind",
            {"pid": pid},
            "guild",
            "admin",
            channels["approval"],
        )

        self.assertEqual(repo.get_pending(pid)["status"], "approved")
        self.assertEqual(channels["member-change"].messages, [])

    async def test_bind_cmd_skips_non_region_approval_channel(self):
        repo.bind_guild("guild", "albion-guild", "Albion Guild", "admin")
        repo.set_setting("guild", "member_role_id", "member-role")
        repo.set_setting("guild", "approval_channel_id", "approval")
        channels = {"approval": FakeChannel("approval", name="✅绑定审批")}
        bot = FakeCommandBot(channels, FakeGuild(FakeUser(["admin-role"], user_id="admin")))
        register.register(bot, FakeGameInfo())
        msg = FakeMessage(FakeChannel("apply", name="eu-📥补装申请"), FakeUser([], user_id="user-1"))

        await bot.commands["绑定"](msg, "Latano")

        self.assertEqual(channels["approval"].messages, [])
        self.assertIsNone(repo.get_open_pending("user-1", "guild"))
        self.assertTrue(any("提交审批失败" in reply for reply in msg.replies))


class FakeUser:
    def __init__(self, roles, user_id="user"):
        self.id = user_id
        self.roles = roles


class FakeRole:
    def __init__(self, role_id, permissions=1):
        self.id = role_id
        self.name = f"role-{role_id}"
        self.permissions = permissions


class FakeGuild:
    def __init__(self, user):
        self.id = "guild"
        self.user = user
        self.master_id = "owner"
        self.granted_roles = []
        self.nicknames = []

    async def load(self):
        return None

    async def fetch_roles(self):
        return [FakeRole("admin-role")]

    async def fetch_user(self, user_id):
        self.user.id = user_id
        return self.user

    async def grant_role(self, user_id, role_id):
        self.granted_roles.append((user_id, role_id))

    async def set_user_nickname(self, user_id, nickname):
        self.nicknames.append((user_id, nickname))


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


class FakeCommandBot(FakeBot):
    def __init__(self, channels, guild):
        super().__init__(channels, guild)
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


class FakeGate:
    def __init__(self):
        self.requests = []

    async def exec_req(self, req):
        self.requests.append(req)
        return {}


class FakeChannel:
    def __init__(self, channel_id, name=None):
        self.id = channel_id
        self.name = name
        self.messages = []

    async def send(self, message):
        self.messages.append(message)
        return {"msg_id": f"msg-{self.id}-{len(self.messages)}"}


class FakeMessage:
    def __init__(self, channel, author):
        self.ctx = type("Ctx", (), {"guild": FakeGuild(author), "channel": channel})()
        self.author = author
        self.replies = []

    async def reply(self, message):
        self.replies.append(message)


class FakeGameInfo:
    async def find_player(self, name):
        return {
            "Id": "player-1",
            "Name": name,
            "GuildId": "albion-guild",
            "GuildName": "Albion Guild",
            "KillFame": 1000,
        }
