"""管理员指令：绑定公会 / 设置 / 解绑公会，以及公会选择按钮事件。"""
import asyncio
import json
import logging
import re

from khl import Bot, EventTypes, Message

from bot import perms
from bot.albion.gameinfo import GameInfo
from bot.cards.admin_cards import MAX_CANDIDATES, guild_select_card
from bot.store import repo

log = logging.getLogger(__name__)

_ROLE_ALL_RE = re.compile(r"\(rol\)(\d+)\(rol\)")

REGEAR_CENTER_CATEGORY_NAME = "🛡️补装中心"
REGEAR_CENTER_CHANNELS = {
    "regear_apply_channel_id": "📥补装申请",
    "regear_review_channel_id": "🔍补装审核",
    "regear_payout_channel_id": "💰补装发放",
    "regear_notify_channel_id": "📣补装通知",
}
REGEAR_SPLIT_CHANNEL_KEYS = {
    "补装申请频道": "regear_apply_channel_id",
    "补装审核频道": "regear_review_channel_id",
    "补装发放频道": "regear_payout_channel_id",
    "补装通知频道": "regear_notify_channel_id",
}
KOOK_PERM_VIEW_CHANNEL = 2048
KOOK_PERM_SEND_MESSAGE = 4096
KOOK_PERM_VIEW_SEND = KOOK_PERM_VIEW_CHANNEL | KOOK_PERM_SEND_MESSAGE


async def _enrich_guild(gi: GameInfo, g: dict) -> dict:
    """补查公会详情，拿会长/联盟/人数，供卡片展示防误绑。"""
    detail = {}
    try:
        detail = await gi.guild(g["Id"])
    except Exception as exc:
        log.warning("拉取公会详情失败 %s: %s", g.get("Id"), exc)
    return {
        "Id": g["Id"],
        "Name": detail.get("Name") or g.get("Name"),
        "Founder": detail.get("FounderName"),
        "Alliance": detail.get("AllianceTag") or detail.get("AllianceName") or g.get("AllianceName"),
        "Members": detail.get("MemberCount"),
    }


async def _resolve_role(guild, value: str):
    """身份组：优先 @提及/数字 id，回退按名字匹配。返回 id 字符串或 None。"""
    rid = perms.parse_role_id(value)
    if rid:
        return rid
    try:
        roles = await guild.fetch_roles()
    except Exception as exc:
        log.warning("拉取身份组失败: %s", exc)
        return None
    for r in roles:
        if r.name == value:
            return str(r.id)
    return None


async def _resolve_channel(guild, value: str):
    """频道：优先 #提及/数字 id，回退按名字匹配。返回 id 字符串或 None。"""
    cid = perms.parse_channel_id(value)
    if cid:
        return cid
    try:
        channels = await guild.fetch_channel_list()
    except Exception as exc:
        log.warning("拉取频道失败: %s", exc)
        return None
    for c in channels:
        if getattr(c, "name", None) == value:
            return c.id
    return None


def _csv_ids(raw: object) -> list[str]:
    return [p.strip() for p in str(raw or "").split(",") if p.strip()]


def _role_type_value(role) -> int:
    role_type = getattr(role, "type", 0)
    return int(getattr(role_type, "value", role_type) or 0)


def _is_manager_role(role) -> bool:
    permissions = int(getattr(role, "permissions", 0) or 0)
    return any((permissions >> bit) & 1 for bit in perms.MANAGE_BITS)


def _is_bot_role(role) -> bool:
    return _role_type_value(role) == 1


async def _create_or_update_role_permission(holder, role_id: str, *, allow: int = 0, deny: int = 0) -> None:
    role_id = str(role_id)
    try:
        await holder.create_role_permission(role_id)
    except Exception as exc:
        log.debug("创建频道身份组权限覆盖失败/已存在 role=%s channel=%s: %s", role_id, getattr(holder, "id", "?"), exc)
    await holder.update_role_permission(role_id, allow=allow, deny=deny)


async def _apply_regear_center_permissions(bot: Bot, guild, channels: dict[str, object], binding: dict) -> list[str]:
    warnings: list[str] = []
    member_role_id = (binding or {}).get("member_role_id")
    reviewer_role_ids = _csv_ids((binding or {}).get("regear_reviewer_role_ids"))
    try:
        roles = await guild.fetch_roles()
    except Exception as exc:
        log.warning("初始化补装中心时拉取身份组失败: %s", exc)
        roles = []
        warnings.append("未能读取身份组，私密频道权限可能需要手动检查。")

    manager_role_ids = [str(r.id) for r in roles if _is_manager_role(r)]
    bot_role_ids = await _guess_bot_role_ids(bot, roles)
    staff_role_ids = sorted(set(reviewer_role_ids + manager_role_ids + bot_role_ids))

    async def apply_perm(field: str, role_id: str, *, allow: int = 0, deny: int = 0) -> None:
        try:
            await _create_or_update_role_permission(channels[field], role_id, allow=allow, deny=deny)
        except Exception as exc:
            log.warning("写补装中心权限失败 channel=%s role=%s: %s", field, role_id, exc)
            warnings.append(f"{REGEAR_CENTER_CHANNELS[field]} 权限写入失败：role {role_id}")

    if member_role_id:
        await apply_perm("regear_apply_channel_id", "0", deny=KOOK_PERM_VIEW_CHANNEL)
        await apply_perm("regear_apply_channel_id", member_role_id, allow=KOOK_PERM_VIEW_SEND)
        await apply_perm("regear_notify_channel_id", "0", deny=KOOK_PERM_VIEW_CHANNEL)
        await apply_perm(
            "regear_notify_channel_id",
            member_role_id,
            allow=KOOK_PERM_VIEW_CHANNEL,
            deny=KOOK_PERM_SEND_MESSAGE,
        )
    else:
        await apply_perm("regear_notify_channel_id", "0", deny=KOOK_PERM_SEND_MESSAGE)
        warnings.append("未设置会员身份组，补装申请频道沿用默认可见性；建议先 `/设置 会员身份组 @身份组`。")

    for role_id in staff_role_ids:
        await apply_perm("regear_apply_channel_id", role_id, allow=KOOK_PERM_VIEW_SEND)

    for field in ("regear_review_channel_id", "regear_payout_channel_id"):
        await apply_perm(field, "0", deny=KOOK_PERM_VIEW_CHANNEL)
        for role_id in staff_role_ids:
            await apply_perm(field, role_id, allow=KOOK_PERM_VIEW_SEND)

    for role_id in sorted(set(manager_role_ids + bot_role_ids)):
        await apply_perm("regear_notify_channel_id", role_id, allow=KOOK_PERM_VIEW_SEND)

    if not reviewer_role_ids:
        warnings.append("未设置补装审核身份组，审核/发放频道目前只显式放行管理身份组和 bot。")
    if not bot_role_ids:
        warnings.append("未识别到 bot 身份组；若 bot 无法在私密频道发卡，请手动给 bot 身份组放行。")
    return warnings


async def _guess_bot_role_ids(bot: Bot, roles: list) -> list[str]:
    bot_roles = [r for r in roles if _is_bot_role(r)]
    if not bot_roles:
        return []
    try:
        me = await bot.client.fetch_me()
    except Exception as exc:
        log.debug("拉取 bot 用户信息失败: %s", exc)
        me = None
    names = {getattr(me, "username", ""), getattr(me, "nickname", "")} if me else set()
    names = {n for n in names if n}
    exact = [r for r in bot_roles if getattr(r, "name", "") in names]
    if exact:
        return [str(r.id) for r in exact]
    fuzzy = [
        r
        for r in bot_roles
        if any(n and n in getattr(r, "name", "") for n in names)
    ]
    return [str(r.id) for r in (fuzzy or bot_roles)]


async def _create_regear_center(bot: Bot, guild, binding: dict) -> tuple[object, dict[str, object], list[str]]:
    category = await guild.create_channel_category(REGEAR_CENTER_CATEGORY_NAME)
    channels = {}
    for field, name in REGEAR_CENTER_CHANNELS.items():
        channels[field] = await guild.create_text_channel(name, category)
    warnings = await _apply_regear_center_permissions(bot, guild, channels, binding)
    return category, channels, warnings


SETTING_USAGE = (
    "用法：\n"
    "`/设置 会员身份组 @身份组`\n"
    "`/设置 审批频道 #频道`\n"
    "`/设置 补装初始化频道`\n"
    "`/设置 补装申请频道 #频道`\n"
    "`/设置 补装审核频道 #频道`\n"
    "`/设置 补装发放频道 #频道`\n"
    "`/设置 补装通知频道 #频道`\n"
    "`/设置 补装频道 #频道`\n"
    "`/设置 补装审核身份组 @身份组[ @身份组...]`\n"
    "`/设置 播报频道 #频道`\n"
    "`/设置 击杀播报频道 #频道`\n"
    "`/设置 阵亡播报频道 #频道`\n"
    "`/设置 战报推送频道 #频道`\n"
    "`/设置 战报本会最小人数 <人数>`\n"
    "`/设置 成员变动频道 #频道`\n"
    "`/设置 可信身份组 @身份组[ @身份组...]`\n"
    "`/设置 大额阈值 <fame数字>`"
)


def register(bot: Bot, gi: GameInfo) -> None:
    @bot.command(name="绑定公会")
    async def bind_guild_cmd(msg: Message, *args):
        name = " ".join(args).strip()
        if not name:
            await msg.reply("用法：/绑定公会 <公会名>")
            return
        if not await perms.is_guild_admin(msg.ctx.guild, msg.author):
            await msg.reply("⛔ 只有管理员可以绑定公会。")
            return
        try:
            guilds = await gi.find_guild(name)
        except Exception as exc:
            log.warning("搜索公会失败: %s", exc)
            await msg.reply("⚠️ 查询公会失败，官方接口可能抽风，稍后再试。")
            return
        if not guilds:
            await msg.reply(f"没搜到公会「{name}」，确认下名字。")
            return
        enriched = await asyncio.gather(
            *[_enrich_guild(gi, g) for g in guilds[:MAX_CANDIDATES]]
        )
        await msg.reply(guild_select_card(msg.ctx.guild.id, list(enriched)))

    @bot.command(name="解绑公会")
    async def unbind_guild_cmd(msg: Message, *args):
        if not await perms.is_guild_admin(msg.ctx.guild, msg.author):
            await msg.reply("⛔ 只有管理员可以解绑公会。")
            return
        ok = repo.unbind_guild(msg.ctx.guild.id)
        await msg.reply("✅ 已解绑公会。" if ok else "本服务器当前没有绑定公会。")

    @bot.command(name="设置")
    async def setting_cmd(msg: Message, *args):
        if not await perms.is_guild_admin(msg.ctx.guild, msg.author):
            await msg.reply("⛔ 只有管理员可以修改设置。")
            return
        kgid = msg.ctx.guild.id
        if not repo.get_guild_binding(kgid):
            await msg.reply("请先 /绑定公会。")
            return
        if not args:
            await msg.reply(SETTING_USAGE)
            return

        key = args[0]
        value = " ".join(args[1:]).strip()

        if key == "会员身份组":
            rid = await _resolve_role(msg.ctx.guild, value)
            if not rid:
                await msg.reply(f"找不到身份组「{value}」。可 @身份组、给 ID，或确认名字完全一致。")
                return
            repo.set_setting(kgid, "member_role_id", rid)
            await msg.reply(f"✅ 会员身份组已设为 (rol){rid}(rol)")

        elif key == "审批频道":
            cid = await _resolve_channel(msg.ctx.guild, value)
            if not cid:
                await msg.reply(f"找不到频道「{value}」。可 #频道、给 ID，或确认名字完全一致。")
                return
            repo.set_setting(kgid, "approval_channel_id", cid)
            await msg.reply(f"✅ 审批频道已设为 (chn){cid}(chn)")

        elif key == "播报频道":
            cid = await _resolve_channel(msg.ctx.guild, value)
            if not cid:
                await msg.reply(f"找不到频道「{value}」。可 #频道、给 ID，或确认名字完全一致。")
                return
            repo.set_setting(kgid, "broadcast_channel_id", cid)
            await msg.reply(f"✅ 播报频道已设为 (chn){cid}(chn)")

        elif key == "击杀播报频道":
            cid = await _resolve_channel(msg.ctx.guild, value)
            if not cid:
                await msg.reply(f"找不到频道「{value}」。可 #频道、给 ID，或确认名字完全一致。")
                return
            repo.set_setting(kgid, "kill_broadcast_channel_id", cid)
            await msg.reply(f"✅ 击杀播报频道已设为 (chn){cid}(chn)")

        elif key in ("阵亡播报频道", "死亡播报频道"):
            cid = await _resolve_channel(msg.ctx.guild, value)
            if not cid:
                await msg.reply(f"找不到频道「{value}」。可 #频道、给 ID，或确认名字完全一致。")
                return
            repo.set_setting(kgid, "death_broadcast_channel_id", cid)
            await msg.reply(f"✅ 阵亡播报频道已设为 (chn){cid}(chn)")

        elif key in ("战报推送频道", "战报频道"):
            cid = await _resolve_channel(msg.ctx.guild, value)
            if not cid:
                await msg.reply(f"找不到频道「{value}」。可 #频道、给 ID，或确认名字完全一致。")
                return
            repo.set_setting(kgid, "battle_report_channel_id", cid)
            await msg.reply(f"✅ 战报推送频道已设为 (chn){cid}(chn)")

        elif key == "战报本会最小人数":
            if not value.isdigit() or int(value) <= 0:
                await msg.reply("战报本会最小人数需为正整数，例：/设置 战报本会最小人数 20")
                return
            repo.set_setting(kgid, "battle_report_min_guild_players", int(value))
            await msg.reply(f"✅ 战报本会最小人数已设为 {int(value)} 人。")

        elif key == "成员变动频道":
            cid = await _resolve_channel(msg.ctx.guild, value)
            if not cid:
                await msg.reply(f"找不到频道「{value}」。可 #频道、给 ID，或确认名字完全一致。")
                return
            repo.set_setting(kgid, "member_change_channel_id", cid)
            await msg.reply(f"✅ 成员变动频道已设为 (chn){cid}(chn)")

        elif key == "补装初始化频道":
            binding = repo.get_guild_binding(kgid) or {}
            try:
                category, channels, warnings = await _create_regear_center(bot, msg.ctx.guild, binding)
            except Exception as exc:
                log.warning("初始化补装中心失败: %s", exc)
                await msg.reply("⚠️ 创建补装中心失败，请检查 bot 是否有管理频道/管理权限。")
                return
            for field, channel in channels.items():
                repo.set_setting(kgid, field, str(channel.id))
            lines = [
                f"✅ 已新建 `{REGEAR_CENTER_CATEGORY_NAME}`，并写入补装频道配置。",
                f"· 分组：`{getattr(category, 'id', '-')}`",
            ]
            for field, name in REGEAR_CENTER_CHANNELS.items():
                lines.append(f"· {name}：(chn){channels[field].id}(chn)")
            if warnings:
                lines.append("⚠️ " + "；".join(dict.fromkeys(warnings)))
            await msg.reply("\n".join(lines))

        elif key in REGEAR_SPLIT_CHANNEL_KEYS:
            cid = await _resolve_channel(msg.ctx.guild, value)
            if not cid:
                await msg.reply(f"找不到频道「{value}」。可 #频道、给 ID，或确认名字完全一致。")
                return
            field = REGEAR_SPLIT_CHANNEL_KEYS[key]
            repo.set_setting(kgid, field, cid)
            await msg.reply(f"✅ {key}已设为 (chn){cid}(chn)")

        elif key == "补装频道":
            cid = await _resolve_channel(msg.ctx.guild, value)
            if not cid:
                await msg.reply(f"找不到频道「{value}」。可 #频道、给 ID，或确认名字完全一致。")
                return
            repo.set_setting(kgid, "regear_channel_id", cid)
            await msg.reply(f"✅ 补装频道已设为 (chn){cid}(chn)")

        elif key == "补装审核身份组":
            rids = _ROLE_ALL_RE.findall(value)
            if not rids:
                for token in value.split():
                    one = await _resolve_role(msg.ctx.guild, token)
                    if one:
                        rids.append(one)
            if not rids:
                await msg.reply(f"找不到身份组「{value}」。可 @身份组，或确认名字。")
                return
            repo.set_setting(kgid, "regear_reviewer_role_ids", ",".join(rids))
            await msg.reply(f"✅ 补装审核身份组已设为 {len(rids)} 个。")

        elif key == "可信身份组":
            rids = _ROLE_ALL_RE.findall(value)
            if not rids:
                # 回退：按名字逐个匹配（空格分隔）
                for token in value.split():
                    one = await _resolve_role(msg.ctx.guild, token)
                    if one:
                        rids.append(one)
            if not rids:
                await msg.reply(f"找不到身份组「{value}」。可 @身份组，或确认名字。")
                return
            repo.set_setting(kgid, "trusted_role_ids", ",".join(rids))
            await msg.reply(f"✅ 可信身份组已设为 {len(rids)} 个（绑定走快速通道）。")

        elif key == "大额阈值":
            if not value.isdigit():
                await msg.reply("阈值需为数字（fame），例：/设置 大额阈值 100000")
                return
            repo.set_setting(kgid, "kill_fame_threshold", int(value))
            await msg.reply(f"✅ 大额播报阈值已设为 {int(value):,} fame。")

        else:
            await msg.reply(SETTING_USAGE)

    @bot.on_event(EventTypes.MESSAGE_BTN_CLICK)
    async def on_btn_click(b: Bot, event):
        body = event.body or {}
        raw = body.get("value") or ""
        try:
            val = json.loads(raw)
        except (ValueError, TypeError):
            return
        if val.get("act") != "bind_guild":
            return

        guild_id = body.get("guild_id")
        user_id = body.get("user_id")
        channel_id = body.get("channel_id") or body.get("target_id")
        gid = val.get("gid")
        kgid = val.get("kgid")
        log.info("收到公会绑定按钮: guild=%s user=%s gid=%s", guild_id, user_id, gid)

        try:
            channel = await b.client.fetch_public_channel(channel_id)
        except Exception as exc:
            log.warning("拉取频道失败: %s", exc)
            return

        try:
            guild = await b.client.fetch_guild(guild_id)
            user = await guild.fetch_user(user_id)
        except Exception as exc:
            log.warning("拉取公会/成员失败: %s", exc)
            await channel.send("⚠️ 校验权限失败，稍后再试。")
            return

        if not await perms.is_guild_admin(guild, user):
            await channel.send("⛔ 只有管理员可以确认绑定。")
            return

        try:
            ginfo = await gi.guild(gid)
            gname = ginfo.get("Name") or gid
        except Exception as exc:
            log.warning("拉取公会详情失败: %s", exc)
            gname = gid

        repo.bind_guild(kgid, gid, gname, user_id)
        await channel.send(
            f"✅ 已将本服务器绑定到公会「{gname}」。\n"
            "下一步：`/设置 会员身份组 @身份组` 和 `/设置 审批频道 #频道`。"
        )
