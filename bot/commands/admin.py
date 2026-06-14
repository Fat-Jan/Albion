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


SETTING_USAGE = (
    "用法：\n"
    "`/设置 会员身份组 @身份组`\n"
    "`/设置 审批频道 #频道`\n"
    "`/设置 补装频道 #频道`\n"
    "`/设置 补装审核身份组 @身份组[ @身份组...]`\n"
    "`/设置 播报频道 #频道`\n"
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
