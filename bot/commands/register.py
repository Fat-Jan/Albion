"""玩家绑定指令：/绑定 /解绑，含角色预检分级 + 审批按钮事件。

流程见实现计划第五节：search 校验角色在本公会 → KOOK 角色预检（可信身份组走
快速通道）→ 否则发审批卡片 → 管理员 [通过]/[拒绝] → 通过则发身份组+改昵称+落库。
"""
import json
import logging

from khl import Bot, EventTypes, Message

from bot import perms
from bot.albion.gameinfo import GameInfo
from bot.cards.register_cards import approval_card, binding_result_card
from bot.commands.kook_message import update_public_message
from bot.store import repo

log = logging.getLogger(__name__)


def _normalize_custom_nickname(value: str | None) -> str | None:
    custom = (value or "").strip()
    while custom.startswith("-"):
        custom = custom[1:].strip()
    return custom or None


def _display_nickname(player_name: str, custom_nickname: str | None = None) -> str:
    custom = _normalize_custom_nickname(custom_nickname)
    return f"{player_name} - {custom}" if custom else player_name


def _parse_bind_args(args: tuple[str, ...]) -> tuple[str | None, str | None]:
    if not args:
        return None, None
    player_name = args[0].strip()
    custom_nickname = _normalize_custom_nickname(" ".join(args[1:]))
    return (player_name or None), custom_nickname


async def _finalize_bind(
    guild,
    kook_user_id: str,
    member_role_id: str,
    player_id: str,
    player_name: str,
    custom_nickname: str | None = None,
) -> list[str]:
    """发身份组 + 改昵称 + 落库。返回告警（部分操作失败但不致命）。"""
    warnings: list[str] = []
    try:
        await guild.grant_role(kook_user_id, member_role_id)
    except Exception as exc:
        log.warning("发身份组失败: %s", exc)
        warnings.append("发身份组失败（检查 bot 身份组是否高于会员组、有管理身份组权限）")
    try:
        await guild.set_user_nickname(kook_user_id, _display_nickname(player_name, custom_nickname))
    except Exception as exc:
        log.warning("改昵称失败: %s", exc)
        warnings.append("改昵称失败（检查 bot 是否有修改他人昵称权限、身份组排序）")
    repo.set_player_binding(kook_user_id, guild.id, player_id, player_name, custom_nickname)
    return warnings


def _bind_notify_channel(guild_binding: dict | None) -> str | None:
    if not guild_binding:
        return None
    return (
        guild_binding.get("member_change_channel_id")
        or guild_binding.get("approval_channel_id")
    )


async def _send_bind_notice(b: Bot, guild_binding: dict | None, fallback_channel, payload) -> None:
    channel_id = _bind_notify_channel(guild_binding)
    if not channel_id:
        await fallback_channel.send(payload)
        return
    try:
        channel = await b.client.fetch_public_channel(channel_id)
    except Exception as exc:
        log.warning("拉取绑定通知频道失败 channel=%s: %s", channel_id, exc)
        await fallback_channel.send(payload)
        return
    await channel.send(payload)


async def _handle_bind_review(b: Bot, act: str, val: dict, guild_id: str, clicker: str, channel) -> None:
    try:
        guild = await b.client.fetch_guild(guild_id)
        clicker_user = await guild.fetch_user(clicker)
    except Exception as exc:
        log.warning("拉取公会/点击者失败: %s", exc)
        await channel.send("⚠️ 校验权限失败，稍后再试。")
        return
    if not await perms.is_guild_admin(guild, clicker_user):
        await channel.send("⛔ 只有管理员可以审批。")
        return

    pending_id = val.get("pid")
    pending = repo.get_pending(pending_id)
    if not pending:
        await channel.send(f"没有找到绑定申请 `#{pending_id or '?'}`，可能已删除或按钮来自旧消息。")
        return
    if pending["status"] != "pending":
        card = binding_result_card(pending)
        await channel.send(card)
        return

    binding = repo.get_guild_binding(guild_id)
    warnings: list[str] = []
    if act == "reject_bind":
        repo.set_pending_status(pending_id, "rejected")
    else:
        if not binding or not binding.get("member_role_id"):
            await channel.send("⚠️ 会员身份组未设置，无法通过。")
            return
        warnings = await _finalize_bind(
            guild,
            pending["kook_user_id"],
            binding["member_role_id"],
            pending["albion_player_id"],
            pending["albion_player_name"],
            pending.get("custom_nickname"),
        )
        repo.set_pending_status(pending_id, "approved")

    pending = repo.get_pending(pending_id) or pending
    card = binding_result_card(pending, warnings=warnings)
    await update_public_message(b.client, pending.get("message_id"), card)
    await _send_bind_notice(b, binding, channel, card)


def register(bot: Bot, gi: GameInfo) -> None:
    @bot.command(name="绑定")
    async def bind_cmd(msg: Message, *args):
        name, custom_nickname = _parse_bind_args(args)
        if not name:
            await msg.reply("用法：/绑定 <游戏角色名> [自定义昵称]，例如 /绑定 BEISHENGS 北笙")
            return

        kgid = msg.ctx.guild.id
        kuid = msg.author.id
        binding = repo.get_guild_binding(kgid)
        if not binding:
            await msg.reply("本服还没绑定公会，请管理员先 /绑定公会。")
            return
        if not binding.get("member_role_id"):
            await msg.reply("管理员还没 /设置 会员身份组。")
            return

        if repo.get_player_binding(kuid, kgid):
            await msg.reply("你已绑定角色，如需更换请先 /解绑。")
            return
        if repo.get_open_pending(kuid, kgid):
            await msg.reply("你有一条绑定申请正在审批中，请耐心等待。")
            return

        try:
            player = await gi.find_player(name)
        except Exception as exc:
            log.warning("搜索角色失败: %s", exc)
            await msg.reply("⚠️ 查询角色失败，官方接口可能抽风，稍后再试。")
            return
        if not player:
            await msg.reply(f"没找到角色「{name}」，确认下名字（大小写不敏感，需完全一致）。")
            return

        if player.get("GuildId") != binding["albion_guild_id"]:
            cur_guild = player.get("GuildName") or "无公会"
            await msg.reply(
                f"角色「{player.get('Name')}」当前公会是「{cur_guild}」，不在本服绑定的"
                f"「{binding['albion_guild_name']}」，无法绑定。"
            )
            return

        dup = repo.get_binding_by_player(kgid, player["Id"])
        if dup:
            await msg.reply("该角色已被本服其他成员绑定，如有异议请联系管理员。")
            return

        # 角色预检分级：持可信身份组 → 快速通道
        trusted = (binding.get("trusted_role_ids") or "").split(",")
        trusted = {t for t in trusted if t}
        user_roles = {str(r) for r in (getattr(msg.author, "roles", []) or [])}
        if trusted and (trusted & user_roles):
            warnings = await _finalize_bind(
                msg.ctx.guild,
                kuid,
                binding["member_role_id"],
                player["Id"],
                player["Name"],
                custom_nickname,
            )
            tip = ("\n⚠️ " + "；".join(warnings)) if warnings else ""
            display_name = _display_nickname(player["Name"], custom_nickname)
            await msg.reply(
                f"✅ 已绑定角色「{player['Name']}」，KOOK 昵称「{display_name}」（可信身份组快速通道）。{tip}"
            )
            return

        # 否则走审批
        if not binding.get("approval_channel_id"):
            await msg.reply("管理员还没 /设置 审批频道，暂时无法提交审批。")
            return
        pending_id = repo.create_pending(kgid, kuid, player["Id"], player["Name"], custom_nickname)
        try:
            channel = await bot.client.fetch_public_channel(binding["approval_channel_id"])
            sent = await channel.send(approval_card(pending_id, kuid, player, custom_nickname))
            msg_id = sent.get("msg_id") if isinstance(sent, dict) else None
            if msg_id:
                repo.set_pending_message(pending_id, msg_id)
        except Exception as exc:
            log.warning("发审批卡片失败: %s", exc)
            repo.set_pending_status(pending_id, "rejected")
            await msg.reply("⚠️ 提交审批失败（检查审批频道是否有效、bot 是否可发言）。")
            return
        await msg.reply(f"📨 已提交「{player['Name']}」的绑定申请，等待管理员审批。")

    @bot.command(name="解绑")
    async def unbind_cmd(msg: Message, *args):
        kgid = msg.ctx.guild.id
        kuid = msg.author.id
        removed = repo.delete_player_binding(kuid, kgid)
        if not removed:
            await msg.reply("你当前没有绑定角色。")
            return
        binding = repo.get_guild_binding(kgid)
        if binding and binding.get("member_role_id"):
            try:
                await msg.ctx.guild.revoke_role(kuid, binding["member_role_id"])
            except Exception as exc:
                log.warning("撤身份组失败: %s", exc)
        await msg.reply(f"✅ 已解绑角色「{removed['albion_player_name']}」。")

    @bot.on_event(EventTypes.MESSAGE_BTN_CLICK)
    async def on_approval_click(b: Bot, event):
        body = event.body or {}
        try:
            val = json.loads(body.get("value") or "")
        except (ValueError, TypeError):
            return
        act = val.get("act")
        if act not in ("approve_bind", "reject_bind"):
            return

        guild_id = body.get("guild_id")
        clicker = body.get("user_id")
        channel_id = body.get("channel_id") or body.get("target_id")

        try:
            channel = await b.client.fetch_public_channel(channel_id)
        except Exception as exc:
            log.warning("拉取审批频道失败: %s", exc)
            return
        await _handle_bind_review(b, act, val, guild_id, clicker, channel)
