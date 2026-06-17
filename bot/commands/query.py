"""查询指令：战绩 / 估值 / 战役 / 物价 / 金价 / 榜单。

已绑定用户免输名字（从 player_binding 取）。
"""
import logging

from khl import Bot, Message

from bot import region_scope
from bot.albion import items, valuation
from bot.albion.gameinfo import GameInfo
from bot.albion.market import ROYAL_CITIES, Market
from bot.cards import query_cards as qc
from bot.store import repo

log = logging.getLogger(__name__)


def register(bot: Bot, gi: GameInfo, mk: Market) -> None:
    @bot.command(name="战绩")
    async def stats_cmd(msg: Message, *args):
        if not region_scope.should_process_message(msg):
            return
        await reply_stats(msg, gi, args)

    @bot.command(name="估值")
    async def value_cmd(msg: Message, *args):
        if not region_scope.should_process_message(msg):
            return
        await reply_valuation(msg, gi, mk, args)

    @bot.command(name="战役")
    async def battle_cmd(msg: Message, *args):
        if not region_scope.should_process_message(msg):
            return
        await reply_battles(msg, gi)

    @bot.command(name="物价")
    async def price_cmd(msg: Message, *args):
        if not region_scope.should_process_message(msg):
            return
        await reply_price(msg, mk, args)

    @bot.command(name="金价")
    async def gold_cmd(msg: Message, *args):
        if not region_scope.should_process_message(msg):
            return
        await reply_gold(msg, mk)

    @bot.command(name="榜单")
    async def rank_cmd(msg: Message, *args):
        if not region_scope.should_process_message(msg):
            return
        await reply_rank(msg, gi, args)


async def _resolve_name(msg: Message, args) -> str | None:
    name = " ".join(str(a) for a in args).strip()
    if name:
        return name
    b = repo.get_player_binding(msg.author.id, msg.ctx.guild.id)
    return b["albion_player_name"] if b else None


async def reply_stats(msg: Message, gi: GameInfo, args=()) -> None:
    name = await _resolve_name(msg, args)
    if not name:
        await msg.reply("先 /绑定，或用 /战绩 <角色名>。")
        return
    try:
        entry = await gi.find_player(name)
        if not entry:
            await msg.reply(f"没找到角色「{name}」。")
            return
        p = await gi.player(entry["Id"])
        kills = await gi.player_kills(entry["Id"])
        deaths = await gi.player_deaths(entry["Id"])
    except Exception as exc:
        log.warning("战绩查询失败: %s", exc)
        await msg.reply("⚠️ 查询失败，官方接口可能抽风，稍后再试。")
        return
    await msg.reply(qc.profile_card(p, len(kills or []), len(deaths or [])))
    await msg.reply(qc.recent_fights_card(entry["Name"], kills, deaths))


async def reply_valuation(msg: Message, gi: GameInfo, mk: Market, args=()) -> None:
    name = await _resolve_name(msg, args)
    if not name:
        await msg.reply("先 /绑定，或用 /估值 <角色名>。")
        return
    try:
        entry = await gi.find_player(name)
        if not entry:
            await msg.reply(f"没找到角色「{name}」。")
            return
        deaths = await gi.player_deaths(entry["Id"])
        if not deaths:
            await msg.reply(f"「{entry['Name']}」最近没有死亡记录。")
            return
        event = deaths[0]
        result = await valuation.estimate(event, mk)
    except Exception as exc:
        log.warning("估值失败: %s", exc)
        await msg.reply("⚠️ 估值失败，稍后再试。")
        return
    await msg.reply(qc.valuation_card(entry["Name"], event, result))


async def reply_battles(msg: Message, gi: GameInfo) -> None:
    binding = repo.get_guild_binding(msg.ctx.guild.id)
    if not binding:
        await msg.reply("本服还没绑定公会，请管理员先 /绑定公会。")
        return
    try:
        battles = await gi.battles(guild_id=binding["albion_guild_id"], limit=5)
    except Exception as exc:
        log.warning("战役查询失败: %s", exc)
        await msg.reply("⚠️ 查询失败，稍后再试。")
        return
    await msg.reply(qc.battles_card(binding["albion_guild_name"], battles or []))


async def reply_price(msg: Message, mk: Market, args=()) -> None:
    query = " ".join(str(a) for a in args).strip()
    if not query:
        await msg.reply("用法：/物价 <物品名或ID>，例：/物价 老手级双剑")
        return
    matches = items.find_by_name(query)
    if not matches:
        await msg.reply(f"没找到物品「{query}」。")
        return
    if len(matches) > 1:
        preview = "、".join(zh for _u, zh in matches[:8])
        await msg.reply(f"匹配到多个，请更具体：{preview}")
        return
    uniq, zh = matches[0]
    try:
        rows = await mk.prices(uniq, locations=ROYAL_CITIES)
    except Exception as exc:
        log.warning("物价查询失败: %s", exc)
        await msg.reply("⚠️ 查询失败，稍后再试。")
        return
    await msg.reply(qc.price_card(rows or [], zh))


async def reply_gold(msg: Message, mk: Market) -> None:
    try:
        data = await mk.gold(count=2)
    except Exception as exc:
        log.warning("金价查询失败: %s", exc)
        await msg.reply("⚠️ 查询失败，稍后再试。")
        return
    if not data:
        await msg.reply("暂无金价数据。")
        return
    latest = data[-1].get("price")
    prev = data[-2].get("price") if len(data) > 1 else None
    await msg.reply(qc.gold_card(latest, prev))


async def reply_rank(msg: Message, gi: GameInfo, args=()) -> None:
    kind = (str(args[0]).lower() if args else "pvp")
    if kind not in ("pvp", "pve"):
        kind = "pvp"
    binding = repo.get_guild_binding(msg.ctx.guild.id)
    if not binding:
        await msg.reply("本服还没绑定公会，请管理员先 /绑定公会。")
        return
    try:
        members = await gi.guild_members(binding["albion_guild_id"])
    except Exception as exc:
        log.warning("榜单查询失败: %s", exc)
        await msg.reply("⚠️ 查询失败，稍后再试。")
        return

    def _val(m):
        if kind == "pvp":
            return m.get("KillFame") or 0
        return ((m.get("LifetimeStatistics") or {}).get("PvE") or {}).get("Total") or 0

    ranked = sorted(members or [], key=_val, reverse=True)[:10]
    ranking = [(m.get("Name"), _val(m)) for m in ranked]
    await msg.reply(qc.leaderboard_card(binding["albion_guild_name"], kind, ranking))
