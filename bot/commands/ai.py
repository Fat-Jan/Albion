"""AI 辅助指令：/助手 /战报 /补装解释。

AI 只做只读解释和摘要，不参与审批、发组、改金额或标记发放。
"""
import logging
import re
from datetime import date, datetime, timedelta

from khl import Bot, Message

from bot.ai.context import regear_explain_context
from bot.ai.router import AIRouter
from bot.ai.service import AIService
from bot.albion import valuation
from bot.albion.gameinfo import GameInfo
from bot.albion.market import Market
from bot.commands import regear as regear_cmds
from bot import perms
from bot.store import repo

log = logging.getLogger(__name__)

BATTLE_REPORT_RECENT_LIMIT = 8
BATTLE_REPORT_DATED_LIMIT = 51


def _parse_battle_report_date(
    args: tuple[object, ...], *, today: date | None = None
) -> date | None:
    raw = "".join(str(a) for a in args).strip()
    if not raw:
        return None
    compact = raw.replace(" ", "").replace("号", "日")
    match = re.fullmatch(
        r"(?:(\d{4})[年./-])?(\d{1,2})(?:月|[./-])(\d{1,2})日?(?:晚|晚上|夜|夜间)?",
        compact,
    )
    if not match:
        raise ValueError("invalid battle report date")
    current_day = today or (datetime.utcnow() + timedelta(hours=8)).date()
    year = int(match.group(1) or current_day.year)
    return date(year, int(match.group(2)), int(match.group(3)))


def _filter_battle_report_battles(battles: list[dict], target: date) -> list[dict]:
    """按北京时间 ZvZ 夜间窗口过滤：目标日 14:30 到次日 05:00。"""
    start_utc = datetime(target.year, target.month, target.day, 14, 30) - timedelta(hours=8)
    next_day = target + timedelta(days=1)
    end_utc = datetime(next_day.year, next_day.month, next_day.day, 5, 0) - timedelta(
        hours=8
    )
    selected: list[dict] = []
    for battle in battles or []:
        started_at = _battle_start_utc(battle)
        if started_at and start_utc <= started_at < end_utc:
            selected.append(battle)
    return selected


def _battle_start_utc(battle: dict) -> datetime | None:
    raw = str(battle.get("startTime") or battle.get("StartTime") or "").strip()
    if not raw:
        return None
    text = raw[:-1] if raw.endswith("Z") else raw
    if "." in text:
        head, frac = text.split(".", 1)
        digits = "".join(ch for ch in frac if ch.isdigit())[:6]
        text = f"{head}.{digits}" if digits else head
    else:
        text = text[:19]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def register(bot: Bot, ai_service: AIService, gi: GameInfo, mk: Market) -> None:
    router = AIRouter(ai_service, gameinfo=gi)

    @bot.command(name="助手")
    async def assistant_cmd(msg: Message, *args):
        question = " ".join(args).strip()
        binding = repo.get_guild_binding(msg.ctx.guild.id)
        can_manage_regear = False
        can_manage_guild = False
        try:
            can_manage_regear = await regear_cmds._can_manage_regear(
                msg.ctx.guild, msg.author, binding
            )
        except Exception as exc:
            log.warning("AI 助手权限探测失败，降级为本人只读范围: %s", exc)
        try:
            can_manage_guild = await perms.is_guild_admin(msg.ctx.guild, msg.author)
        except Exception as exc:
            log.warning("AI 助手管理员权限探测失败，降级为非管理员范围: %s", exc)
        answer = await router.answer(
            msg.ctx.guild.id,
            msg.author.id,
            question,
            can_manage_regear=can_manage_regear,
            can_manage_guild=can_manage_guild,
        )
        await msg.reply(answer)

    @bot.command(name="战报")
    async def battle_report_cmd(msg: Message, *args):
        binding = repo.get_guild_binding(msg.ctx.guild.id)
        if not binding:
            await msg.reply("本服还没绑定公会，请管理员先 /绑定公会。")
            return
        try:
            target_date = _parse_battle_report_date(args)
        except ValueError:
            await msg.reply("用法：`/战报` 或 `/战报 6-15`（按北京时间晚间窗口）。")
            return
        limit = BATTLE_REPORT_DATED_LIMIT if target_date else BATTLE_REPORT_RECENT_LIMIT
        try:
            battles = await gi.battles(guild_id=binding["albion_guild_id"], limit=limit)
        except Exception as exc:
            log.warning("战报拉取失败: %s", exc)
            await msg.reply("⚠️ 查询战役失败，稍后再试。")
            return
        if target_date:
            battles = _filter_battle_report_battles(battles or [], target_date)
            if not battles:
                next_day = target_date + timedelta(days=1)
                await msg.reply(
                    "没有查到 "
                    f"{target_date:%Y-%m-%d} 14:30 到 {next_day:%Y-%m-%d} 05:00 "
                    "（北京时间）的战役记录。"
                )
                return
        text = await ai_service.summarize_battles(binding["albion_guild_name"], battles or [])
        if not text:
            await msg.reply("AI 暂时不可用；可以先用 `/战役` 查看最近战役。")
            return
        if target_date:
            next_day = target_date + timedelta(days=1)
            text = (
                f"查询范围：北京时间 {target_date:%Y-%m-%d} 14:30 "
                f"至 {next_day:%Y-%m-%d} 05:00。\n{text}"
            )
        await msg.reply(text)

    @bot.command(name="补装解释")
    async def regear_explain_cmd(msg: Message, *args):
        if not args or not str(args[0]).isdigit():
            await msg.reply("用法：`/补装解释 <申请号>`")
            return
        rid = int(args[0])
        rr = repo.get_regear(rid)
        if not rr or rr.get("kook_guild_id") != msg.ctx.guild.id:
            await msg.reply("没有找到这条补装申请。")
            return
        if rr.get("kook_user_id") != msg.author.id:
            gbind = repo.get_guild_binding(msg.ctx.guild.id)
            if not await regear_cmds._can_manage_regear(msg.ctx.guild, msg.author, gbind):
                await msg.reply("⛔ 只有申请人、管理员或补装审核身份组可以查看补装解释。")
                return
        try:
            ev = await gi.event(rr["event_id"])
            result = await valuation.estimate(ev, mk)
        except Exception as exc:
            log.warning("补装解释事实包生成失败: %s", exc)
            await msg.reply("⚠️ 查询补装详情失败，稍后再试。")
            return
        facts = regear_explain_context(rr, ev, result)
        text = await ai_service.explain_regear(facts)
        if not text:
            await msg.reply("AI 暂时不可用；补装金额仍以审批卡片和数据库记录为准。")
            return
        await msg.reply("AI 辅助说明，仅供参考：\n" + text)
