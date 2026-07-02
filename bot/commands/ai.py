"""AI 辅助指令：/助手 /战报 /补装解释。

AI 只做只读解释和摘要，不参与审批、发组、改金额或标记发放。
"""
import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from khl import Bot, Message

from bot import config, region_scope
from bot.ai.context import regear_explain_context
from bot.ai.router import AIRouter, _looks_mutating
from bot.ai.service import AIService
from bot.albion import valuation
from bot.albion.gameinfo import GameInfo
from bot.albion.market import Market
from bot.commands import query as query_cmds
from bot.commands import regear as regear_cmds
from bot import perms
from bot.store import repo

log = logging.getLogger(__name__)

BATTLE_REPORT_RECENT_LIMIT = 8
BATTLE_REPORT_DATED_LIMIT = 51


@dataclass(frozen=True)
class MentionIntent:
    action: str
    question: str
    args: tuple[str, ...] = ()


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
    current_day = today or (datetime.now(UTC) + timedelta(hours=8)).date()
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


def _bot_mention_names(names: tuple[str, ...] | None = None) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            name.strip().lstrip("@")
            for name in (names if names is not None else config.KOOK_BOT_MENTION_ALIASES)
            if name.strip().lstrip("@")
        )
    )


def _strip_bot_mention(
    content: str, bot_id: str, names: tuple[str, ...] | None = None
) -> str:
    text = (content or "").strip()
    if bot_id:
        patterns = (
            rf"\(met\)\s*{re.escape(bot_id)}\s*\(met\)",
            rf"<@!?\s*{re.escape(bot_id)}\s*>",
        )
        for pattern in patterns:
            text = re.sub(pattern, " ", text)
    for name in _bot_mention_names(names):
        text = re.sub(rf"(^|\s)@{re.escape(name)}(?=\s|$)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_mention_intent(question: str, *, today: date | None = None) -> MentionIntent:
    q = (question or "").strip()
    if not q:
        return MentionIntent("assistant", q)
    if _looks_mutating(q):
        return MentionIntent("assistant", q)
    if "补装解释" in q:
        match = re.search(r"#?\s*(\d+)", q)
        return MentionIntent("regear_explain", q, (match.group(1),) if match else ())
    if "金价" in q:
        return MentionIntent("gold", q)
    if "物价" in q or "价格" in q:
        item = _clean_query_arg(re.sub(r"(物价|价格)", "", q))
        return MentionIntent("price", q, (item,) if item else ())
    if "榜单" in q or "排行" in q or "排名" in q:
        kind = "pve" if re.search(r"\bpve\b|采集|刷怪|打怪", q, re.IGNORECASE) else "pvp"
        return MentionIntent("rank", q, (kind,))
    if "战绩" in q:
        name = _extract_subject_around(q, "战绩")
        return MentionIntent("stats", q, (name,) if name else ())
    if "估值" in q or "估一下" in q or "估价" in q:
        marker = "估值" if "估值" in q else "估价" if "估价" in q else "最近死亡"
        name = _extract_subject_around(q, marker)
        return MentionIntent("valuation", q, (name,) if name else ())
    date_arg = _extract_battle_report_date_arg(q, today=today)
    if "战役" in q and not any(word in q for word in ("战役总结", "战斗报告")):
        if date_arg:
            return MentionIntent("battle_report", q, (date_arg,))
        return MentionIntent("battles", q)
    if any(word in q for word in ("战报", "战役总结", "战斗报告")):
        return MentionIntent("battle_report", q, (date_arg,) if date_arg else ())
    return MentionIntent("assistant", q)


def _extract_battle_report_date_arg(
    question: str, *, today: date | None = None
) -> str | None:
    compact = question.replace(" ", "")
    patterns = (
        r"(?:(?:20)?\d{2}[年./-])?\d{1,2}(?:月|[./-])\d{1,2}日?",
        r"今天|今日|昨晚|昨夜|昨天晚上|昨日晚上|昨天|昨日",
    )
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            value = match.group(0)
            current_day = today or (datetime.now(UTC) + timedelta(hours=8)).date()
            if value in {"今天", "今日"}:
                return f"{current_day.month}-{current_day.day}"
            if value in {"昨晚", "昨夜", "昨天晚上", "昨日晚上", "昨天", "昨日"}:
                yesterday = current_day - timedelta(days=1)
                return f"{yesterday.month}-{yesterday.day}"
            return value
    return None


def _extract_subject_around(question: str, marker: str) -> str | None:
    text = question
    if marker in text:
        before, after = text.split(marker, 1)
        before = re.sub(r"(最近死亡|最近阵亡|死亡|阵亡)$", "", before).strip()
        return _clean_query_arg(before) or _clean_query_arg(after)
    text = re.sub(r"(最近死亡|最近阵亡|死亡|阵亡)$", "", text).strip()
    return _clean_query_arg(text)


def _clean_query_arg(text: str) -> str | None:
    cleaned = str(text or "").strip()
    cleaned = re.sub(
        r"^(帮我|帮忙|麻烦|请|查询|查一下|查|看一下|看看|看|调用|打开|来个|给我|估一下|估|一下)+",
        "",
        cleaned,
    )
    cleaned = re.sub(r"(的|一下|看看|查询|查|看)$", "", cleaned).strip()
    cleaned = cleaned.strip(" ，,。")
    if cleaned in {"", "我", "我的", "自己", "本人"}:
        return None
    return cleaned


def _message_mentions_bot(
    msg: Message, bot_id: str, names: tuple[str, ...] | None = None
) -> bool:
    if not bot_id or bot_id == "unknown":
        return False
    mentions = [str(item) for item in getattr(msg, "mention", []) or []]
    if bot_id in mentions:
        return True
    content = getattr(msg, "content", "") or ""
    if f"(met){bot_id}(met)" in content:
        return True
    return any(
        re.search(rf"(^|\s)@{re.escape(name)}(?=\s|$)", content)
        for name in _bot_mention_names(names)
    )


def register(
    bot: Bot, ai_service: AIService, gi: GameInfo, mk: Market, *, region: str = "eu"
) -> None:
    router = AIRouter(ai_service, gameinfo=gi)
    region_cfg = config.REGION_CONFIGS.get(region)
    bot_id = config.token_runtime_info(region_cfg.kook_token if region_cfg else "")["bot_id"]

    @bot.command(name="助手")
    async def assistant_cmd(msg: Message, *args):
        if region_scope.is_other_region_channel(msg.ctx.channel, region=region):
            return
        question = " ".join(args).strip()
        await _reply_assistant(msg, router, question, region=region)

    @bot.command(name="战报")
    async def battle_report_cmd(msg: Message, *args):
        if not region_scope.should_process_message(msg, region=region):
            return
        await _reply_battle_report(msg, ai_service, gi, args, region=region)

    @bot.command(name="补装解释")
    async def regear_explain_cmd(msg: Message, *args):
        if not region_scope.should_process_message(msg, region=region):
            return
        await _reply_regear_explain(msg, ai_service, gi, mk, args, region=region)

    @bot.on_message()
    async def mention_assistant(msg: Message):
        if not getattr(getattr(msg, "ctx", None), "guild", None):
            return
        author_id = getattr(msg, "author_id", None) or getattr(
            getattr(msg, "author", None), "id", ""
        )
        if str(author_id) == bot_id:
            return
        if not _message_mentions_bot(msg, bot_id):
            return
        if region_scope.is_other_region_channel(msg.ctx.channel, region=region):
            return
        log.debug(
            "AI mention received channel=%s guild=%s region=%s",
            getattr(msg.ctx.channel, "name", "?"),
            getattr(msg.ctx.guild, "id", "?"),
            region,
        )
        question = _strip_bot_mention(msg.content, bot_id)
        intent = _parse_mention_intent(question)
        log.info(
            "AI mention 路由 action=%s has_args=%s guild=%s channel=%s author=%s",
            intent.action,
            bool(intent.args),
            getattr(msg.ctx.guild, "id", "?"),
            getattr(msg.ctx.channel, "id", "?"),
            author_id,
        )
        if intent.action == "battle_report":
            await _reply_battle_report(msg, ai_service, gi, intent.args, region=region)
            return
        if intent.action == "regear_explain":
            await _reply_regear_explain(msg, ai_service, gi, mk, intent.args, region=region)
            return
        if intent.action == "stats":
            await query_cmds.reply_stats(msg, gi, intent.args, region=region)
            return
        if intent.action == "valuation":
            await query_cmds.reply_valuation(msg, gi, mk, intent.args, region=region)
            return
        if intent.action == "battles":
            await query_cmds.reply_battles(msg, gi, region=region)
            return
        if intent.action == "price":
            await query_cmds.reply_price(msg, mk, intent.args)
            return
        if intent.action == "gold":
            await query_cmds.reply_gold(msg, mk)
            return
        if intent.action == "rank":
            await query_cmds.reply_rank(msg, gi, intent.args, region=region)
            return
        await _reply_assistant(msg, router, intent.question, region=region)


async def _reply_assistant(
    msg: Message, router: AIRouter, question: str, *, region: str = "eu"
) -> None:
    binding = repo.get_guild_binding(msg.ctx.guild.id, region)
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


async def _reply_battle_report(
    msg: Message,
    ai_service: AIService,
    gi: GameInfo,
    args: tuple[object, ...],
    *,
    region: str = "eu",
) -> None:
    binding = repo.get_guild_binding(msg.ctx.guild.id, region)
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


async def _reply_regear_explain(
    msg: Message,
    ai_service: AIService,
    gi: GameInfo,
    mk: Market,
    args: tuple[object, ...],
    *,
    region: str = "eu",
) -> None:
    if not args or not str(args[0]).isdigit():
        await msg.reply("用法：`/补装解释 <申请号>`")
        return
    rid = int(args[0])
    rr = repo.get_regear(rid)
    if not rr or rr.get("kook_guild_id") != msg.ctx.guild.id:
        await msg.reply("没有找到这条补装申请。")
        return
    if rr.get("kook_user_id") != msg.author.id:
        gbind = repo.get_guild_binding(msg.ctx.guild.id, region)
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
