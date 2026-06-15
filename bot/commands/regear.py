"""补装指令：/补装 列最近死亡 → 选一个 → 估值 → 审核 → 发放 → 通知。

复用估值（valuation）+ 审批流（按钮事件）。新配置走申请/审核/发放/通知四频道，
旧 `regear_channel_id` 保留为单频道兼容兜底。
"""
import json
import logging

from khl import Bot, EventTypes, Message

from bot import perms
from bot.albion import valuation
from bot.albion.gameinfo import GameInfo
from bot.albion.market import Market
from bot.cards.query_cards import beijing_datetime
from bot.cards.regear_cards import (
    PAYOUT_METHOD_LABELS,
    death_detail_card,
    death_select_card,
    regear_apply_card,
    regear_approved_card,
    regear_notice_card,
    regear_queue_card,
    regear_reviewer_apply_card,
    regear_reviewer_result_card,
)
from bot.commands.kook_message import update_public_message
from bot.store import repo

log = logging.getLogger(__name__)

_QUEUE_FILTERS = {
    "待处理": ("pending",),
    "待审批": ("pending",),
    "待发放": ("approved",),
    "已通过": ("approved",),
    "列表": None,
    "全部": None,
}
_PAYOUT_METHOD_ALIASES = {
    "silver": "silver",
    "银币": "silver",
    "等额银币": "silver",
    "等额游戏银币": "silver",
    "equipment": "equipment",
    "装备": "equipment",
    "原样装备": "equipment",
    "原装备": "equipment",
    "item": "item",
    "物品": "item",
    "等价值物品": "item",
    "等价物品": "item",
}


def _first_channel(guild_binding: dict | None, *fields: str) -> str | None:
    if not guild_binding:
        return None
    for field in fields:
        value = guild_binding.get(field)
        if value:
            return value
    return None


def _regear_apply_channel(guild_binding: dict | None) -> str | None:
    return _first_channel(
        guild_binding,
        "regear_apply_channel_id",
        "regear_channel_id",
        "approval_channel_id",
    )


def _regear_review_channel(guild_binding: dict | None) -> str | None:
    return _first_channel(
        guild_binding,
        "regear_review_channel_id",
        "regear_channel_id",
        "approval_channel_id",
    )


def _regear_payout_channel(guild_binding: dict | None) -> str | None:
    return _first_channel(
        guild_binding,
        "regear_payout_channel_id",
        "regear_channel_id",
        "approval_channel_id",
    )


def _regear_notify_channel(guild_binding: dict | None) -> str | None:
    return _first_channel(
        guild_binding,
        "regear_notify_channel_id",
        "regear_channel_id",
        "approval_channel_id",
    )


def _regear_approval_channel(guild_binding: dict | None) -> str | None:
    return _regear_review_channel(guild_binding)


async def _send_regear_notice(b: Bot, guild_binding: dict | None, payload) -> None:
    notify_channel_id = _regear_notify_channel(guild_binding)
    if not notify_channel_id:
        return
    try:
        notify_channel = await b.client.fetch_public_channel(notify_channel_id)
        await notify_channel.send(payload)
    except Exception as exc:
        log.warning("发送补装通知失败 channel=%s: %s", notify_channel_id, exc)


def _regear_reviewer_notify_channel(guild_binding: dict | None) -> str | None:
    return _first_channel(guild_binding, "member_change_channel_id", "approval_channel_id")


async def _send_regear_reviewer_notice(b: Bot, guild_binding: dict | None, fallback_channel, payload) -> None:
    channel_id = _regear_reviewer_notify_channel(guild_binding)
    if not channel_id:
        await fallback_channel.send(payload)
        return
    try:
        channel = await b.client.fetch_public_channel(channel_id)
    except Exception as exc:
        log.warning("拉取补装审核身份通知频道失败 channel=%s: %s", channel_id, exc)
        await fallback_channel.send(payload)
        return
    await channel.send(payload)


def _regear_paid_notice(regear_row: dict) -> str:
    rid = regear_row.get("id") or "?"
    user_id = regear_row.get("kook_user_id") or "?"
    paid_at = beijing_datetime(regear_row.get("paid_at")) or "未知"
    method = _payout_method_label(regear_row.get("payout_method"))
    return (
        f"✅ 补装申请 `#{rid}` 已发放：(met){user_id}(met)\n"
        f"状态：已发放　处理时间：`{paid_at}`　方式：`{method}`"
    )


def _regear_rejected_notice(regear_row: dict) -> str:
    rid = regear_row.get("id") or "?"
    user_id = regear_row.get("kook_user_id") or "?"
    reviewed_at = beijing_datetime(regear_row.get("reviewed_at")) or "未知"
    reason = regear_row.get("reject_reason") or "未填写"
    return (
        f"❌ 补装申请 `#{rid}` 已拒绝：(met){user_id}(met)\n"
        f"状态：已拒绝　处理时间：`{reviewed_at}`　原因：`{reason}`"
    )


def _payout_method_label(method: str | None) -> str:
    return PAYOUT_METHOD_LABELS.get(method or "", method or "未记录")


def _normalize_payout_method(raw: str | None) -> str | None:
    if not raw:
        return None
    return _PAYOUT_METHOD_ALIASES.get(str(raw).strip())


def _regear_processed_text(regear_row: dict) -> str:
    rid = regear_row.get("id") or "?"
    user_id = regear_row.get("kook_user_id") or "?"
    status = regear_row.get("status") or "?"
    if status == "paid":
        return (
            f"补装申请 `#{rid}` 已发放：(met){user_id}(met)\n"
            f"处理时间：`{beijing_datetime(regear_row.get('paid_at')) or '未知'}`　"
            f"处理人：(met){regear_row.get('paid_by') or '-'}(met)　"
            f"方式：`{_payout_method_label(regear_row.get('payout_method'))}`"
        )
    if status == "rejected":
        return (
            f"补装申请 `#{rid}` 已拒绝：(met){user_id}(met)\n"
            f"处理时间：`{beijing_datetime(regear_row.get('reviewed_at')) or '未知'}`　"
            f"处理人：(met){regear_row.get('reviewed_by') or '-'}(met)　"
            f"原因：`{regear_row.get('reject_reason') or '未填写'}`"
        )
    if status == "approved":
        return (
            f"补装申请 `#{rid}` 已通过，等待发放：(met){user_id}(met)\n"
            f"审核时间：`{beijing_datetime(regear_row.get('reviewed_at')) or '未知'}`　"
            f"审核人：(met){regear_row.get('reviewed_by') or '-'}(met)"
        )
    if status == "pending":
        return f"补装申请 `#{rid}` 仍在待审批状态：(met){user_id}(met)"
    return f"补装申请 `#{rid}` 当前状态：`{status}`：(met){user_id}(met)"


def _parse_regear_id(raw: str | None) -> int | None:
    if not raw:
        return None
    text = str(raw).strip().lstrip("#")
    return int(text) if text.isdigit() else None


def _configured_regear_reviewer_roles(guild_binding: dict | None) -> set[str]:
    raw = (guild_binding or {}).get("regear_reviewer_role_ids") or ""
    return {r.strip() for r in raw.split(",") if r.strip()}


def _has_regear_reviewer_role(user, guild_binding: dict | None) -> bool:
    configured = _configured_regear_reviewer_roles(guild_binding)
    if not configured:
        return False
    user_roles = {str(r) for r in (getattr(user, "roles", []) or [])}
    return bool(configured & user_roles)


async def _can_manage_regear(guild, user, guild_binding: dict | None = None) -> bool:
    if await perms.is_guild_admin(guild, user):
        return True
    binding = guild_binding if guild_binding is not None else repo.get_guild_binding(guild.id)
    return _has_regear_reviewer_role(user, binding)


def register(bot: Bot, gi: GameInfo, mk: Market) -> None:
    @bot.command(name="补装")
    async def regear_cmd(msg: Message, *args):
        if args:
            if args[0] in ("状态", "进度", "我的"):
                await _handle_status_cmd(msg)
                return
            await _handle_queue_cmd(bot, gi, mk, msg, args)
            return

        kgid = msg.ctx.guild.id
        binding = repo.get_player_binding(msg.author.id, kgid)
        if not binding:
            await msg.reply("请先 /绑定 你的游戏角色，再申请补装。")
            return
        gbind = repo.get_guild_binding(kgid)
        if not _regear_review_channel(gbind):
            await msg.reply("管理员还没 /设置 补装审核频道，暂时无法申请补装。")
            return
        try:
            deaths = await gi.player_deaths(binding["albion_player_id"])
        except Exception as exc:
            log.warning("拉取死亡失败: %s", exc)
            await msg.reply("⚠️ 查询失败，稍后再试。")
            return
        if not deaths:
            await msg.reply("你最近没有死亡记录。")
            return
        estimates = await _estimate_death_candidates(deaths, mk)
        await msg.reply(death_select_card(binding["albion_player_name"], deaths, estimates=estimates))

    @bot.command(name="补装状态")
    async def regear_status_cmd(msg: Message, *args):
        await _handle_status_cmd(msg)

    @bot.command(name="补装审核")
    async def regear_reviewer_cmd(msg: Message, *args):
        kgid = msg.ctx.guild.id
        kuid = msg.author.id
        gbind = repo.get_guild_binding(kgid)
        if not gbind:
            await msg.reply("本服还没绑定公会，请管理员先 /绑定公会。")
            return
        if not _configured_regear_reviewer_roles(gbind):
            await msg.reply("管理员还没 /设置 补装审核身份组，暂时无法申请。")
            return
        if _has_regear_reviewer_role(msg.author, gbind):
            await msg.reply("你已经有补装审核身份组了。")
            return
        if repo.get_open_regear_reviewer_request(kgid, kuid):
            await msg.reply("你已有一条补装审核身份申请正在审批中，请耐心等待。")
            return
        approval_channel_id = gbind.get("approval_channel_id") or _regear_approval_channel(gbind)
        if not approval_channel_id:
            await msg.reply("管理员还没 /设置 审批频道，暂时无法提交补装审核身份申请。")
            return

        request_id = repo.create_regear_reviewer_request(kgid, kuid)
        try:
            approval = await bot.client.fetch_public_channel(approval_channel_id)
            sent = await approval.send(regear_reviewer_apply_card(request_id, kuid))
            msg_id = sent.get("msg_id") if isinstance(sent, dict) else None
            if msg_id:
                repo.set_regear_reviewer_request_message(request_id, msg_id)
        except Exception as exc:
            log.warning("发补装审核身份申请卡片失败: %s", exc)
            repo.set_regear_reviewer_request_status(request_id, "rejected", "system")
            await msg.reply("⚠️ 提交失败（检查审批频道）。")
            return
        await msg.reply("📨 已提交补装审核身份申请，等待管理员审批。")

    @bot.on_event(EventTypes.MESSAGE_BTN_CLICK)
    async def on_regear_click(b: Bot, event):
        body = event.body or {}
        try:
            val = json.loads(body.get("value") or "")
        except (ValueError, TypeError):
            return
        act = val.get("act")
        if act not in (
            "regear_pick",
            "regear_detail",
            "regear_approve",
            "regear_reject",
            "regear_paid",
            "regear_reviewer_approve",
            "regear_reviewer_reject",
        ):
            return

        guild_id = body.get("guild_id")
        clicker = body.get("user_id")
        channel_id = body.get("channel_id") or body.get("target_id")
        try:
            channel = await b.client.fetch_public_channel(channel_id)
        except Exception as exc:
            log.warning("拉取频道失败: %s", exc)
            return

        if act == "regear_detail":
            await _handle_detail(b, gi, mk, val, channel)
        elif act == "regear_pick":
            await _handle_pick(b, gi, mk, val, guild_id, clicker, channel)
        elif act in ("regear_reviewer_approve", "regear_reviewer_reject"):
            await _handle_reviewer_request_review(b, act, val, guild_id, clicker, channel)
        else:
            await _handle_review(b, gi, mk, act, val, guild_id, clicker, channel)


async def _load_regear_valuation(regear_row: dict, gi: GameInfo, mk: Market) -> tuple[dict | None, dict | None]:
    try:
        event_id = regear_row.get("event_id")
        if not event_id:
            return None, None
        ev = await gi.event(event_id)
        result = await valuation.estimate(ev, mk)
        return ev, result
    except Exception as exc:
        log.warning("补装通知明细加载失败 request=%s: %s", regear_row.get("id"), exc)
        return None, None


async def _update_regear_source_card(b: Bot, regear_row: dict, card) -> bool:
    return await update_public_message(b.client, regear_row.get("message_id"), card)


async def _handle_queue_cmd(b: Bot, gi: GameInfo, mk: Market, msg: Message, args):
    key = args[0]
    if key in ("拒绝", "驳回"):
        await _handle_reject_cmd(b, gi, mk, msg, args)
        return
    if key in ("发放", "已发放"):
        await _handle_paid_cmd(b, gi, mk, msg, args)
        return
    if key not in _QUEUE_FILTERS:
        await msg.reply(
            "用法：`/补装`、`/补装 待处理|待发放|列表`、"
            "`/补装 拒绝 #申请号 理由`、`/补装 发放 #申请号 银币|装备|物品 [备注]`"
        )
        return
    gbind = repo.get_guild_binding(msg.ctx.guild.id)
    if not await _can_manage_regear(msg.ctx.guild, msg.author, gbind):
        await msg.reply("⛔ 只有管理员或补装审核身份组可以查看补装队列。")
        return
    statuses = _QUEUE_FILTERS[key]
    rows = repo.list_regear(msg.ctx.guild.id, statuses=statuses, limit=10)
    await msg.reply(regear_queue_card(f"补装{key}", rows))


async def _handle_reject_cmd(b: Bot, gi: GameInfo, mk: Market, msg: Message, args):
    if len(args) < 3:
        await msg.reply("用法：`/补装 拒绝 #申请号 理由文本`")
        return
    rid = _parse_regear_id(args[1])
    reason = " ".join(str(a) for a in args[2:]).strip()
    if not rid or not reason:
        await msg.reply("用法：`/补装 拒绝 #申请号 理由文本`")
        return
    gbind = repo.get_guild_binding(msg.ctx.guild.id)
    if not await _can_manage_regear(msg.ctx.guild, msg.author, gbind):
        await msg.reply("⛔ 只有管理员或补装审核身份组可以拒绝补装。")
        return
    rr = repo.get_regear(rid)
    if not rr or rr.get("kook_guild_id") != msg.ctx.guild.id:
        await msg.reply("没有找到这条补装申请。")
        return
    if rr.get("status") != "pending":
        await msg.reply(_regear_processed_text(rr))
        return
    ev, result = await _load_regear_valuation(rr, gi, mk)
    repo.set_regear_rejected(rid, msg.author.id, reason)
    rr = repo.get_regear(rid) or rr
    card = regear_notice_card(rr, ev, result)
    await _update_regear_source_card(b, rr, card)
    await msg.reply(card)
    await _send_regear_notice(b, gbind, card)


async def _handle_paid_cmd(b: Bot, gi: GameInfo, mk: Market, msg: Message, args):
    if len(args) < 3:
        await msg.reply("用法：`/补装 发放 #申请号 银币|装备|物品 [备注]`")
        return
    rid = _parse_regear_id(args[1])
    method = _normalize_payout_method(args[2])
    note = " ".join(str(a) for a in args[3:]).strip() or None
    if not rid or not method:
        await msg.reply("用法：`/补装 发放 #申请号 银币|装备|物品 [备注]`")
        return
    gbind = repo.get_guild_binding(msg.ctx.guild.id)
    if not await _can_manage_regear(msg.ctx.guild, msg.author, gbind):
        await msg.reply("⛔ 只有管理员或补装审核身份组可以标记发放。")
        return
    rr = repo.get_regear(rid)
    if not rr or rr.get("kook_guild_id") != msg.ctx.guild.id:
        await msg.reply("没有找到这条补装申请。")
        return
    if rr.get("status") != "approved":
        await msg.reply(_regear_processed_text(rr))
        return
    ev, result = await _load_regear_valuation(rr, gi, mk)
    repo.set_regear_paid(rid, msg.author.id, method, note)
    rr = repo.get_regear(rid) or rr
    card = regear_notice_card(rr, ev, result)
    await _update_regear_source_card(b, rr, card)
    await msg.reply(card)
    await _send_regear_notice(b, gbind, card)


async def _handle_status_cmd(msg: Message):
    rows = repo.list_user_regear(msg.ctx.guild.id, msg.author.id, limit=5)
    await msg.reply(_regear_status_text(rows))


def _regear_status_text(rows: list[dict]) -> str:
    if not rows:
        return "你最近没有补装申请。"
    from bot.cards.query_cards import fmt

    status_zh = {
        "pending": "待审批",
        "approved": "待发放",
        "rejected": "已拒绝",
        "paid": "已发放",
    }
    lines = ["你的最近补装申请："]
    for row in rows[:5]:
        status = status_zh.get(row.get("status"), row.get("status") or "?")
        line = f"· `#{row['id']}` {status}　金额 `{fmt(row.get('est_value'))}` 银"
        if row.get("status") == "paid":
            line += (
                f"　处理时间 `{beijing_datetime(row.get('paid_at')) or '未知'}`"
                f"　方式 `{_payout_method_label(row.get('payout_method'))}`"
            )
        elif row.get("status") == "rejected":
            line += (
                f"　处理时间 `{beijing_datetime(row.get('reviewed_at')) or '未知'}`"
                f"　原因 `{row.get('reject_reason') or '未填写'}`"
            )
        elif row.get("status") == "approved" and row.get("reviewed_at"):
            line += f"　审核时间 `{beijing_datetime(row.get('reviewed_at'))}`"
        lines.append(line)
    return "\n".join(lines)


async def _estimate_death_candidates(deaths: list[dict], market: Market, max_n: int = 5) -> dict[str, int]:
    estimates: dict[str, int] = {}
    for ev in deaths[:max_n]:
        eid = ev.get("EventId")
        if not eid:
            continue
        try:
            result = await valuation.estimate(ev, market)
        except Exception as exc:
            log.debug("补装候选死亡估值失败 event=%s: %s", eid, exc)
            continue
        estimates[str(eid)] = int(result.get("total") or 0)
    return estimates


async def _handle_detail(b, gi, mk, val, channel):
    eid = val.get("eid")
    try:
        ev = await gi.event(eid)
        result = await valuation.estimate(ev, mk)
    except Exception as exc:
        log.warning("死亡详情估值失败: %s", exc)
        await channel.send("⚠️ 查询详情失败，稍后再试。")
        return
    # 战役总人数：用于推测是否 ZvZ 尖刀/炸弹小队（失败不阻断详情）
    battle_players = 0
    bid = ev.get("BattleId")
    if bid:
        try:
            battle = await gi.battle(bid)
            players = (battle or {}).get("players")
            battle_players = len(players) if isinstance(players, (list, dict)) else 0
        except Exception as exc:
            log.debug("查战役人数失败: %s", exc)
    victim_name = (ev.get("Victim") or {}).get("Name", "?")
    await channel.send(death_detail_card(victim_name, ev, result, battle_players))


async def _handle_pick(b, gi, mk, val, guild_id, clicker, channel):
    binding = repo.get_player_binding(clicker, guild_id)
    if not binding:
        await channel.send("请先 /绑定 角色再申请补装。")
        return
    gbind = repo.get_guild_binding(guild_id)
    review_channel_id = _regear_review_channel(gbind)
    if not review_channel_id:
        await channel.send("管理员还没 /设置 补装审核频道。")
        return
    eid = val.get("eid")
    try:
        ev = await gi.event(eid)
        result = await valuation.estimate(ev, mk)
    except Exception as exc:
        log.warning("补装估值失败: %s", exc)
        await channel.send("⚠️ 估值失败，稍后再试。")
        return

    rid = repo.create_regear(
        guild_id, clicker, binding["albion_player_id"], str(eid), result["total"]
    )
    try:
        review_channel = await b.client.fetch_public_channel(review_channel_id)
        sent = await review_channel.send(
            regear_apply_card(rid, clicker, binding["albion_player_name"], ev, result["total"], result)
        )
        msg_id = sent.get("msg_id") if isinstance(sent, dict) else None
        if msg_id:
            repo.set_regear_message(rid, msg_id)
    except Exception as exc:
        log.warning("发补装审批卡片失败: %s", exc)
        repo.set_regear_status(rid, "rejected", "system")
        await channel.send("⚠️ 提交失败（检查补装审核频道）。")
        return
    await channel.send(
        f"📨 已提交补装申请 `#{rid}`（补装金额 ≈ {result['total']:,} 银，仅计算穿戴装备；背包不计入），等待管理员审批。"
    )


async def _refresh_regear_valuation(regear_id: int, gi: GameInfo, mk: Market) -> tuple[dict, dict]:
    rr = repo.get_regear(regear_id)
    if not rr:
        raise ValueError(f"regear request not found: {regear_id}")
    ev = await gi.event(rr["event_id"])
    result = await valuation.estimate(ev, mk)
    repo.update_regear_est_value(regear_id, result["total"])
    return ev, result


async def _refresh_regear_estimate(regear_id: int, gi: GameInfo, mk: Market) -> int:
    _, result = await _refresh_regear_valuation(regear_id, gi, mk)
    return int(result["total"])


async def _handle_review(b, gi, mk, act, val, guild_id, clicker, channel):
    try:
        guild = await b.client.fetch_guild(guild_id)
        clicker_user = await guild.fetch_user(clicker)
    except Exception as exc:
        log.warning("拉取公会/点击者失败: %s", exc)
        await channel.send("⚠️ 校验权限失败，稍后再试。")
        return
    gbind = repo.get_guild_binding(guild_id)
    if not await _can_manage_regear(guild, clicker_user, gbind):
        await channel.send("⛔ 只有管理员或补装审核身份组可以审批补装。")
        return

    rid = val.get("rid")
    rr = repo.get_regear(rid)
    if not rr:
        await channel.send(f"没有找到补装申请 `#{rid or '?'}`，可能已删除或按钮来自旧消息。")
        return

    if act == "regear_paid":
        if rr["status"] != "approved":
            await channel.send(_regear_processed_text(rr))
            return
        method = _normalize_payout_method(val.get("method"))
        if not method:
            await channel.send(
                f"请选择发放方式后再标记：`/补装 发放 #{rid} 银币|装备|物品 [备注]`"
            )
            return
        ev, result = await _load_regear_valuation(rr, gi, mk)
        repo.set_regear_paid(rid, clicker, method)
        rr = repo.get_regear(rid) or rr
        card = regear_notice_card(rr, ev, result)
        await _update_regear_source_card(b, rr, card)
        await channel.send(card)
        await _send_regear_notice(b, gbind, card)
        return

    if rr["status"] != "pending":
        await channel.send(_regear_processed_text(rr))
        return

    if act == "regear_reject":
        reason = str(val.get("reason") or "").strip()
        if not reason:
            await channel.send(f"请选择拒绝理由，或使用 `/补装 拒绝 #{rid} 理由文本`。")
            return
        ev, result = await _load_regear_valuation(rr, gi, mk)
        repo.set_regear_rejected(rid, clicker, reason)
        rr = repo.get_regear(rid) or rr
        card = regear_notice_card(rr, ev, result)
        await _update_regear_source_card(b, rr, card)
        await channel.send(card)
        await _send_regear_notice(b, gbind, card)
        return
    ev = None
    result = None
    try:
        ev, result = await _refresh_regear_valuation(rid, gi, mk)
        rr = repo.get_regear(rid) or rr
    except Exception as exc:
        log.warning("审批前刷新补装估值失败，沿用旧值: %s", exc)
    repo.set_regear_status(rid, "approved", clicker)
    rr = repo.get_regear(rid) or rr
    notice_card = regear_notice_card(rr, ev, result)
    await _update_regear_source_card(b, rr, notice_card)
    await _send_regear_notice(b, gbind, notice_card)
    payout_channel_id = _regear_payout_channel(gbind)
    if not payout_channel_id or payout_channel_id == getattr(channel, "id", None):
        await channel.send(regear_approved_card(rr, ev, result))
        return
    try:
        payout_channel = await b.client.fetch_public_channel(payout_channel_id)
        sent = await payout_channel.send(regear_approved_card(rr, ev, result))
        msg_id = sent.get("msg_id") if isinstance(sent, dict) else None
        if msg_id:
            repo.set_regear_message(rid, msg_id)
        await channel.send(f"✅ 已通过 (met){rr['kook_user_id']}(met) 的补装申请，已转到发放频道。")
    except Exception as exc:
        log.warning("发送补装发放卡片失败 channel=%s: %s", payout_channel_id, exc)
        await channel.send("⚠️ 发放频道发送失败，已在当前频道生成待发放卡。")
        await channel.send(regear_approved_card(rr, ev, result))


async def _handle_reviewer_request_review(b, act, val, guild_id, clicker, channel):
    try:
        guild = await b.client.fetch_guild(guild_id)
        clicker_user = await guild.fetch_user(clicker)
    except Exception as exc:
        log.warning("拉取公会/点击者失败: %s", exc)
        await channel.send("⚠️ 校验权限失败，稍后再试。")
        return
    if not await perms.is_guild_admin(guild, clicker_user):
        await channel.send("⛔ 只有管理员可以审批补装审核身份。")
        return

    request_id = val.get("rid")
    req = repo.get_regear_reviewer_request(request_id)
    if not req:
        await channel.send(f"没有找到补装审核身份申请 `#{request_id or '?'}`，可能已删除或按钮来自旧消息。")
        return
    if req["status"] != "pending":
        await channel.send(regear_reviewer_result_card(req))
        return

    if act == "regear_reviewer_reject":
        repo.set_regear_reviewer_request_status(request_id, "rejected", clicker)
        req = repo.get_regear_reviewer_request(request_id) or req
        card = regear_reviewer_result_card(req)
        await update_public_message(b.client, req.get("message_id"), card)
        await _send_regear_reviewer_notice(b, repo.get_guild_binding(guild_id), channel, card)
        return

    binding = repo.get_guild_binding(guild_id)
    role_ids = sorted(_configured_regear_reviewer_roles(binding))
    if not role_ids:
        await channel.send("⚠️ 未设置补装审核身份组，无法通过。请先 `/设置 补装审核身份组 @身份组`。")
        return

    warnings: list[str] = []
    for role_id in role_ids:
        try:
            await guild.grant_role(req["kook_user_id"], int(role_id) if role_id.isdigit() else role_id)
        except Exception as exc:
            log.warning("发补装审核身份组失败 role=%s: %s", role_id, exc)
            warnings.append(f"(rol){role_id}(rol)")

    repo.set_regear_reviewer_request_status(request_id, "approved", clicker)
    req = repo.get_regear_reviewer_request(request_id) or req
    notice_warnings = []
    if warnings:
        notice_warnings.append("部分身份组发放失败，请检查 bot 身份组排序和管理身份组权限：" + " ".join(warnings))
    card = regear_reviewer_result_card(req, warnings=notice_warnings)
    await update_public_message(b.client, req.get("message_id"), card)
    await _send_regear_reviewer_notice(b, binding, channel, card)
