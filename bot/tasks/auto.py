"""定时任务：死亡播报 + 退会复查。共用 khl 调度器（apscheduler）。

- 死亡播报：普通时段每 4 分钟轮询全局 /events（多页），20:00-00:30 每 90 秒，
  筛出本会击杀/阵亡推到播报频道，
  大额（TotalVictimKillFame ≥ 阈值）高亮。首轮只记录不播报，避免开机刷历史。
  注：官方 /events?guildId= 只回本会"击杀"不含"阵亡"，故改走全局 feed 双向筛
  （全局事件量随区服波动；ZvZ 突发超覆盖会丢少量，已记日志）。
- 退会复查：每日比对公会成员，已绑定但退会的撤身份组 + 清绑定，并优先通知成员变动频道。
- ZvZ 战报：按专属战报频道配置，在配置的展示时区窗口拉取 AlbionBB
  候选战役，官方详情聚合后推送，并用 SQLite 持久去重。
"""
import logging
from collections import deque
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from khl import Bot

from bot import config
from bot.ai.service import AIService
from bot.albion.battle_report import build_battle_report
from bot.albion import valuation
from bot.albion.gameinfo import GameInfo
from bot.albion.market import Market
from bot.albion import price_reference
from bot.cards.battle_report_cards import battle_report_card
from bot.cards.broadcast_cards import kill_card
from bot.store import repo

log = logging.getLogger(__name__)

BROADCAST_CHECK_INTERVAL_SEC = 30
BROADCAST_INTERVAL_SEC = 4 * 60
BROADCAST_BUSY_INTERVAL_SEC = 90
BROADCAST_INTERVAL_TOLERANCE_SEC = 0.5
BROADCAST_BUSY_START = time(20, 0)
BROADCAST_BUSY_END = time(0, 30)
FEED_PAGES = 4  # 每轮拉的全局 feed 页数（51/页），覆盖轮询间隔内的事件量
MAX_BROADCAST_PER_TICK = 15  # 控频，避免刷爆 KOOK 配额
BATTLE_REPORT_INTERVAL_MIN = 15
BATTLE_REPORT_MIN_PLAYERS = 20
BATTLE_REPORT_START = None
BATTLE_REPORT_END = None

# 去重状态（内存，全局按 EventId）
_seen: set = set()
_seen_order: deque = deque(maxlen=2000)
_primed = False
_price_ref_refreshing = False
_last_death_broadcast_at: datetime | None = None


def _remember(eid) -> None:
    if eid in _seen:
        return
    if len(_seen_order) == _seen_order.maxlen:
        _seen.discard(_seen_order[0])
    _seen_order.append(eid)
    _seen.add(eid)


def classify(event: dict, albion_guild_id: str) -> tuple[bool, bool]:
    """返回 (我方是否击杀, 我方是否阵亡)，0 声望事件不播报。"""
    if (event.get("TotalVictimKillFame") or 0) <= 0:
        return False, False
    is_kill = (event.get("Killer") or {}).get("GuildId") == albion_guild_id
    is_death = (event.get("Victim") or {}).get("GuildId") == albion_guild_id
    return is_kill, is_death


def _member_review_notify_channel(guild_binding: dict) -> str | None:
    return (
        guild_binding.get("member_change_channel_id")
        or guild_binding.get("broadcast_channel_id")
        or guild_binding.get("death_broadcast_channel_id")
        or guild_binding.get("kill_broadcast_channel_id")
        or guild_binding.get("approval_channel_id")
    )


def _has_broadcast_target(guild_binding: dict) -> bool:
    return bool(
        guild_binding.get("broadcast_channel_id")
        or guild_binding.get("kill_broadcast_channel_id")
        or guild_binding.get("death_broadcast_channel_id")
    )


def _broadcast_channel_for_event(
    guild_binding: dict, *, is_kill: bool, is_death: bool
) -> str | None:
    if is_kill:
        return guild_binding.get("kill_broadcast_channel_id") or guild_binding.get(
            "broadcast_channel_id"
        )
    if is_death:
        return guild_binding.get("death_broadcast_channel_id") or guild_binding.get(
            "broadcast_channel_id"
        )
    return None


def _death_broadcast_interval_seconds(now: datetime | None = None) -> int:
    current = (now or datetime.now()).time()
    if current >= BROADCAST_BUSY_START or current < BROADCAST_BUSY_END:
        return BROADCAST_BUSY_INTERVAL_SEC
    return BROADCAST_INTERVAL_SEC


def _should_run_death_broadcast(
    now: datetime, last_run: datetime | None
) -> bool:
    if last_run is None:
        return True
    elapsed = (now - last_run).total_seconds()
    return elapsed + BROADCAST_INTERVAL_TOLERANCE_SEC >= _death_broadcast_interval_seconds(now)


def _should_run_battle_report(now: datetime | None = None) -> bool:
    """战报只在配置的 ZvZ 活跃时段运行；测试传入 naive UTC 时间。"""
    current = _display_datetime(now or datetime.utcnow())
    t = current.time()
    start = _battle_report_window_start()
    end = _battle_report_window_end()
    if start <= end:
        return start <= t < end
    return t >= start or t < end


def _display_datetime(dt: datetime) -> datetime:
    try:
        tz = ZoneInfo(config.DISPLAY_TZ)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("Asia/Shanghai")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(tz)


def _parse_hhmm(value: str, default: time) -> time:
    try:
        hour, minute = str(value).split(":", 1)
        return time(int(hour), int(minute))
    except (TypeError, ValueError):
        return default


def _battle_report_window_start() -> time:
    if isinstance(BATTLE_REPORT_START, time):
        return BATTLE_REPORT_START
    return _parse_hhmm(config.BATTLE_REPORT_WINDOW_START, time(14, 30))


def _battle_report_window_end() -> time:
    if isinstance(BATTLE_REPORT_END, time):
        return BATTLE_REPORT_END
    return _parse_hhmm(config.BATTLE_REPORT_WINDOW_END, time(5, 0))


def _battle_candidate_id(row: dict[str, Any]) -> str:
    for key in ("albionId", "id", "Id", "battleId", "BattleId"):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _candidate_mentions_guild(row: dict[str, Any], guild_name: str) -> bool:
    target = str(guild_name or "").casefold()
    if not target:
        return False
    guilds = row.get("guilds") or row.get("Guilds") or []
    if isinstance(guilds, dict):
        guilds = guilds.values()
    for guild in guilds:
        if not isinstance(guild, dict):
            continue
        name = guild.get("name") or guild.get("Name")
        if str(name or "").casefold() == target:
            return True
    return False


def _configured_battle_report_bindings() -> list[dict]:
    return [
        gb
        for gb in repo.all_guild_bindings()
        if gb.get("battle_report_channel_id") and gb.get("albion_guild_name")
    ]


async def _run_battle_report_tick(
    bot: Bot,
    gi: GameInfo,
    bb_client,
    *,
    now: datetime | None = None,
    ai_service: AIService | None = None,
) -> None:
    if not _should_run_battle_report(now):
        return
    bindings = _configured_battle_report_bindings()
    if not bindings:
        return

    try:
        candidates = await bb_client.albionbb_get(
            "/battles", params={"minPlayers": BATTLE_REPORT_MIN_PLAYERS, "page": 1}
        )
    except Exception as exc:
        log.warning("拉取 AlbionBB 战役列表失败: %s", exc)
        return
    if not isinstance(candidates, list):
        log.warning("AlbionBB 战役列表格式异常: %s", type(candidates).__name__)
        return

    for gb in bindings:
        kgid = gb["kook_guild_id"]
        guild_name = gb["albion_guild_name"]
        min_guild_players = int(
            gb.get("battle_report_min_guild_players") or BATTLE_REPORT_MIN_PLAYERS
        )
        for row in candidates:
            if not isinstance(row, dict) or not _candidate_mentions_guild(row, guild_name):
                continue
            battle_id = _battle_candidate_id(row)
            if not battle_id or repo.has_seen_battle_report(kgid, battle_id):
                continue
            try:
                detail = await gi.battle(battle_id)
                events = await gi.battle_events(battle_id)
                report = build_battle_report(detail, events, guild_name=guild_name)
            except Exception as exc:
                log.warning("生成战报失败 battle=%s guild=%s: %s", battle_id, guild_name, exc)
                continue
            if report.get("guild_players", 0) < min_guild_players:
                continue
            ai_summary = await _ai_battle_report_summary(ai_service, report)
            try:
                channel = await bot.client.fetch_public_channel(gb["battle_report_channel_id"])
                await channel.send(battle_report_card(report, ai_summary=ai_summary))
            except Exception as exc:
                log.warning("推送战报失败 battle=%s guild=%s: %s", battle_id, guild_name, exc)
                continue
            repo.mark_battle_report_seen(kgid, battle_id)


async def _ai_battle_report_summary(ai_service: AIService | None, report: dict) -> str:
    if not ai_service:
        return ""
    try:
        return await ai_service.summarize_battle_report(report)
    except Exception as exc:
        log.warning("生成 AI 战报摘要失败 battle=%s: %s", report.get("battle_id"), exc)
        return ""


def register(bot: Bot, gi: GameInfo, mk: Market, ai_service: AIService | None = None) -> None:
    @bot.task.add_interval(seconds=BROADCAST_CHECK_INTERVAL_SEC)
    async def death_broadcast():
        global _last_death_broadcast_at, _primed
        targets = {
            gb["albion_guild_id"]: gb
            for gb in repo.all_guild_bindings()
            if _has_broadcast_target(gb)
        }
        if not targets:
            return
        now = datetime.now()
        if not _should_run_death_broadcast(now, _last_death_broadcast_at):
            return
        _last_death_broadcast_at = now

        events: list = []
        for off in range(0, FEED_PAGES * 51, 51):
            try:
                page = await gi.events(limit=51, offset=off)
            except Exception as exc:
                log.warning("全局 feed 轮询失败 offset=%s: %s", off, exc)
                break
            events.extend(page or [])

        if not _primed:
            for ev in events:
                _remember(ev.get("EventId"))
            _primed = True
            return

        new_events = [ev for ev in events if ev.get("EventId") not in _seen]
        sent = 0
        for ev in sorted(new_events, key=lambda e: e.get("TimeStamp") or ""):  # 旧→新
            _remember(ev.get("EventId"))
            fame = ev.get("TotalVictimKillFame") or 0
            for agid, gb in targets.items():
                is_kill, is_death = classify(ev, agid)
                if not (is_kill or is_death):
                    continue
                channel_id = _broadcast_channel_for_event(
                    gb, is_kill=is_kill, is_death=is_death
                )
                if not channel_id:
                    continue
                if sent >= MAX_BROADCAST_PER_TICK:
                    log.info("播报达单轮上限 %d，其余下轮再发", MAX_BROADCAST_PER_TICK)
                    return
                try:
                    channel = await bot.client.fetch_public_channel(channel_id)
                    threshold = gb.get("kill_fame_threshold") or 100000
                    est = None
                    if is_death:
                        try:
                            est = await valuation.estimate(ev, mk)
                        except Exception as exc:
                            log.warning("阵亡播报估值失败 event=%s: %s", ev.get("EventId"), exc)
                    await channel.send(kill_card(ev, is_kill, fame >= threshold, est))
                    sent += 1
                except Exception as exc:
                    log.warning("发播报失败: %s", exc)

    @bot.task.add_cron(hour=4, minute=0)
    async def member_review():
        for gb in repo.all_guild_bindings():
            role = gb.get("member_role_id")
            if not role:
                continue
            kgid = gb["kook_guild_id"]
            agid = gb["albion_guild_id"]
            try:
                members = await gi.guild_members(agid)
            except Exception as exc:
                log.warning("退会复查拉成员失败 guild=%s: %s", agid, exc)
                continue
            member_ids = {m.get("Id") for m in (members or [])}
            if not member_ids:
                continue  # 拉空可能是接口抽风，跳过避免误撤

            notify_id = _member_review_notify_channel(gb)
            for pb in repo.list_player_bindings(kgid):
                if pb["albion_player_id"] in member_ids:
                    continue
                try:
                    guild = await bot.client.fetch_guild(kgid)
                    await guild.revoke_role(pb["kook_user_id"], role)
                except Exception as exc:
                    log.warning("退会撤组失败: %s", exc)
                repo.delete_player_binding(pb["kook_user_id"], kgid)
                if notify_id:
                    try:
                        ch = await bot.client.fetch_public_channel(notify_id)
                        await ch.send(
                            f"🚪 (met){pb['kook_user_id']}(met) 的角色"
                            f"「{pb['albion_player_name']}」已退会，已撤销会员身份组。"
                        )
                    except Exception as exc:
                        log.warning("退会通知失败: %s", exc)

    @bot.task.add_interval(minutes=price_reference.REF_REFRESH_INTERVAL_MIN)
    async def weapon_price_reference_refresh():
        global _price_ref_refreshing
        if _price_ref_refreshing:
            return
        _price_ref_refreshing = True
        try:
            stats = await price_reference.refresh_weapon_price_reference(mk)
            log.info(
                "武器/副手低价参考刷新完成: items=%s api_rows=%s records=%s",
                stats["items"],
                stats["api_rows"],
                stats["records"],
            )
        except Exception as exc:
            log.warning("武器/副手低价参考刷新失败: %s", exc)
        finally:
            _price_ref_refreshing = False

    @bot.task.add_interval(minutes=BATTLE_REPORT_INTERVAL_MIN)
    async def battle_report():
        await _run_battle_report_tick(bot, gi, gi.c, ai_service=ai_service)
