"""查询类卡片：战绩 / 估值 / 战役 / 物价 / 金价 / 榜单。"""
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from khl.card import Card, CardMessage, Element, Module, Types

from bot.albion import items
from bot.albion import valuation
from bot import config
from bot.cards.layout import interleave_dividers, kmd_section


def beijing(ts_iso: str) -> str:
    """UTC ISO 时间串 → 配置的展示时区 `MM-DD HH:MM`。"""
    if not ts_iso:
        return ""
    try:
        dt = _parse_utc(ts_iso)
    except ValueError:
        return ""
    return _to_display_tz(dt).strftime("%m-%d %H:%M")


def beijing_datetime(ts: object) -> str:
    """UTC 数据库/API 时间 → 完整展示时区时间，用于审批/处理记录。"""
    raw = str(ts or "").strip()
    if not raw:
        return ""
    try:
        dt = _parse_utc(raw)
    except ValueError:
        return raw
    return f"{_to_display_tz(dt):%Y-%m-%d %H:%M:%S} {config.DISPLAY_TZ_LABEL}"


def display_time_prefix() -> str:
    return config.DISPLAY_TZ_SHORT_LABEL


def display_time_label() -> str:
    return config.DISPLAY_TZ_LABEL


def killboard_url(event_id) -> str:
    return KILLBOARD_URL.format(eid=event_id)


def _parse_utc(raw: str) -> datetime:
    text = str(raw or "").strip()
    if text.endswith("Z"):
        text = text[:-1]
    dt = datetime.fromisoformat(text[:19])
    return dt.replace(tzinfo=UTC)


def _to_display_tz(dt: datetime) -> datetime:
    try:
        tz = ZoneInfo(config.DISPLAY_TZ)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("Asia/Shanghai")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(tz)


class _KillboardURL:
    """兼容旧的 KILLBOARD_URL.format(eid=...) 调用，server 运行时读配置。"""

    def format(self, *, eid, **_: object) -> str:
        return (
            "https://albiononline.com/killboard/kill/"
            f"{eid}?server={config.KILLBOARD_SERVER}"
        )

    def __str__(self) -> str:
        return "https://albiononline.com/killboard/kill/{eid}?server=<configured>"


KILLBOARD_URL = _KillboardURL()

# 官方死亡事件 Location 常为 null，回退 KillArea 粗分类的中文
_AREA_ZH = {
    "OPEN_WORLD": "开放世界",
    "CITY": "城市",
    "DUNGEON": "随机地下城",
    "AVALON_DUNGEON": "阿瓦隆地下城",
    "HELLGATE": "地狱门",
    "ARENA": "竞技场",
    "CRYSTAL_LEAGUE": "水晶联赛",
    "MISTS": "迷雾",
    "STATIC_DUNGEON": "固定地下城",
    "EXPEDITION": "远征",
}


def location_of(event: dict) -> str:
    """死亡地点：Location 优先，回退 KillArea 中文，再回退「未知」。

    迷雾事件官方在 Location/KillArea 里以含 MIST 的标识出现时归「迷雾」；
    但实测当前 gameinfo 数据这两个字段常为 null / OPEN_WORLD，区分不了。
    """
    loc = event.get("Location")
    if loc:
        return "迷雾" if "MIST" in str(loc).upper() else str(loc)
    area = event.get("KillArea")
    if area:
        if "MIST" in str(area).upper():
            return "迷雾"
        return _AREA_ZH.get(area, area)
    return "未知"


def scale_label(event: dict) -> str:
    """按「你方小队人数」(GroupMembers) 粗分规模（预估，免额外查询）。

    GroupMembers 是事件主角所在编组（实测恒含主角本人），比 numberOfParticipants
    （只是补刀人数，常被大战役误标小团）准。整场战役口径由详情卡单独查 /battles。
    返回如「团战·18人(预估)」；无数据返回空串。
    """
    members = event.get("GroupMembers")
    n = len(members) if isinstance(members, list) and members else 0
    if n <= 0:
        n = event.get("numberOfParticipants") or 0
    if n <= 0:
        return ""
    if n == 1:
        tag = "单人"
    elif n <= 7:
        tag = "小团"
    elif n <= 20:
        tag = "团战"
    else:
        tag = "ZvZ"
    return f"{tag}·{n}人(预估)"


def battle_scale_line(event: dict, battle_players: int) -> str:
    """详情卡用：整场战役口径的规模行（你队 + 整场 + 类别 + 尖刀小队推测）。

    battle_players 为 /battles/{id} 的 players 总数；无效时回退 scale_label（队伍口径）。
    """
    if battle_players <= 0:
        return scale_label(event)
    if battle_players <= 6:
        cat = "小规模"
    elif battle_players <= 30:
        cat = "小团"
    elif battle_players <= 80:
        cat = "团战"
    else:
        cat = "ZvZ"
    members = event.get("GroupMembers")
    team_n = len(members) if isinstance(members, list) and members else 0
    parts = []
    if team_n:
        parts.append(f"你队 {team_n} 人")
    parts.append(f"整场 {battle_players} 人")
    line = "　".join(parts) + f"　{cat}(预估)"
    if team_n and team_n <= 10 and battle_players >= 40:
        line += "　⚡尖刀/炸弹小队?(推测)"
    return line


def fmt(n) -> str:
    """大数字转中文可读：亿 / 万。"""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    if abs(n) >= 1e8:
        return f"{n / 1e8:.2f}亿"
    if abs(n) >= 1e4:
        return f"{n / 1e4:.1f}万"
    return f"{int(n):,}"


def profile_card(p: dict, kills: int, deaths: int) -> CardMessage:
    ls = p.get("LifetimeStatistics") or {}
    def total_at(value, *keys):
        for key in keys:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value

    pve = total_at(ls, "PvE", "Total")
    gather = total_at(ls, "Gathering", "All", "Total")
    craft = total_at(ls, "Crafting", "Total")
    identity = [f"角色：`{p.get('Name')}`", f"公会：`{p.get('GuildName') or '无'}`"]
    if p.get("AllianceName"):
        identity.append(f"联盟：`{p.get('AllianceName')}`")
    card = Card(
        *interleave_dividers(
            [
                kmd_section("身份", identity),
                kmd_section(
                    "战斗",
                    [
                        f"击杀声望 `{fmt(p.get('KillFame'))}`　死亡声望 `{fmt(p.get('DeathFame'))}`",
                        f"KD `{p.get('FameRatio')}`",
                    ],
                ),
                kmd_section(
                    "成长",
                    [
                        f"PvE 声望 `{fmt(pve)}`　采集声望 `{fmt(gather)}`",
                        f"制造声望 `{fmt(craft)}`",
                    ],
                ),
                kmd_section("近期", [f"最近击杀 `{kills}`　最近死亡 `{deaths}`"]),
            ]
        )
    )
    return CardMessage(card)


def recent_fights_card(player_name: str, kills: list, deaths: list, n: int = 10) -> CardMessage:
    """最近 N 条击杀 / 阵亡明细（文字）。kills/deaths 为 gameinfo 事件列表。"""

    def line(ev: dict, is_kill: bool) -> str:
        bj = beijing(ev.get("TimeStamp") or "")
        opp = (ev.get("Victim") if is_kill else ev.get("Killer")) or {}
        name = opp.get("Name", "?")
        guild = opp.get("GuildName") or "无"
        fame = fmt(ev.get("TotalVictimKillFame") or 0)
        ip = (opp.get("AverageItemPower") or 0)
        when = f"`{bj}`　" if bj else ""
        return f"· {when}`{name}` [{guild}]　声望 {fame}　IP `{ip:.0f}`"

    klines = [line(e, True) for e in (kills or [])[:n]] or ["（无记录）"]
    dlines = [line(e, False) for e in (deaths or [])[:n]] or ["（无记录）"]
    card = Card(
        Module.Header(f"{player_name} 最近战斗（时间为{display_time_prefix()}）"),
        Module.Section(Element.Text(f"**⚔️ 最近击杀 {len(kills or [])}**\n" + "\n".join(klines), Types.Text.KMD)),
        Module.Divider(),
        Module.Section(Element.Text(f"**💀 最近阵亡 {len(deaths or [])}**\n" + "\n".join(dlines), Types.Text.KMD)),
    )
    return CardMessage(card)


def value_lines(result: dict, equip_limit: int = 10, bag_limit: int = 6) -> list[str]:
    """估值明细文字行：装备槽全列（无价标「无市场价」），背包列有价 top N，其余汇总。"""
    items_list = result.get("items") or []
    equips = sorted((b for b in items_list if b.get("slot")), key=lambda x: -x["value"])
    bag_nonzero = sorted(
        (b for b in items_list if not b.get("slot") and b["value"] > 0), key=lambda x: -x["value"]
    )
    lines: list[str] = []
    for b in equips[:equip_limit]:
        te = items.tier_enchant(b["type"])
        tag = f" [{te}]" if te else ""
        amt = fmt(b["value"]) if b["value"] > 0 else "无市场价"
        lines.append(f"· {items.localized(b['type'])}{tag} ×{b['count']} = {amt}")
    for b in bag_nonzero[:bag_limit]:
        te = items.tier_enchant(b["type"])
        tag = f" [{te}]" if te else ""
        lines.append(f"· {items.localized(b['type'])}{tag} ×{b['count']} = {fmt(b['value'])}")
    shown = len(equips[:equip_limit]) + len(bag_nonzero[:bag_limit])
    skipped = len(items_list) - shown
    if skipped > 0:
        lines.append(f"（另 {skipped} 件背包杂物/无价略）")
    return lines


def valuation_card(player_name: str, event: dict, result: dict) -> CardMessage:
    """单次死亡估值卡（/估值）：装备槽全列、无价标注、缺价回退当前挂单。"""
    victim = event.get("Victim") or {}
    raw = event.get("TimeStamp", "")
    ts = raw[:19].replace("T", " ")
    bj = beijing(raw)
    when = f"`{ts} UTC`（{display_time_prefix()} {bj}）" if bj else f"`{ts}`"
    scale = scale_label(event)
    loc_line = f"时间 {when}　IP `{victim.get('AverageItemPower', 0):.0f}`"
    if scale:
        loc_line += f"　{scale}"
    sums = valuation.summary(result)
    detail_lines = value_lines(result) or ["（暂无可估值明细）"]
    card = Card(
        *interleave_dividers(
            [
                kmd_section("死亡概况", [f"角色：`{player_name}`", loc_line]),
                kmd_section(
                    "损失估值",
                    [
                        (
                            f"装备估值 ≈ `{fmt(sums['equipment_total'])}` 银　"
                            f"背包估值 ≈ `{fmt(sums['inventory_total'])}` 银"
                        ),
                        f"总损失 ≈ `{fmt(sums['loss_total'])}` 银（补装默认只按装备估值）",
                    ],
                ),
                kmd_section("明细", detail_lines),
            ]
        )
    )
    eid = event.get("EventId")
    if eid:
        card.append(
            Module.ActionGroup(
                Element.Button(
                    "查看官方击杀板",
                    KILLBOARD_URL.format(eid=eid),
                    Types.Click.LINK,
                    Types.Theme.SECONDARY,
                )
            )
        )
    return CardMessage(card)


def battles_card(guild_name: str, battles: list) -> CardMessage:
    lines = [f"**{guild_name}** 最近 ZvZ 战役"]
    for b in battles[:5]:
        raw = b.get("startTime") or b.get("StartTime") or ""
        ts = raw[:16].replace("T", " ")
        bj = beijing(raw)
        when = f"`{ts} UTC`（{display_time_prefix()} {bj}）" if bj else f"`{ts}`"
        kills = b.get("totalKills", "?")
        fame = b.get("totalFame", 0)
        players = b.get("totalPlayers", "?")
        lines.append(f"· {when}　击杀 {kills}　声望 {fmt(fame)}　{players} 人")
    if len(lines) == 1:
        lines.append("近期没有战役记录。")
    return CardMessage(Card(Module.Section(Element.Text("\n".join(lines), Types.Text.KMD))))


def price_card(rows: list, item_name: str) -> CardMessage:
    lines = [f"**{item_name}** 现价（各城最低卖单）"]
    shown = 0
    for r in rows:
        sp = r.get("sell_price_min")
        if not sp:
            continue
        city = r.get("city")
        q = r.get("quality")
        lines.append(f"· {city}（Q{q}）`{fmt(sp)}`")
        shown += 1
    if shown == 0:
        lines.append("各城暂无挂单（当前区服市场数据稀疏）。")
    return CardMessage(Card(Module.Section(Element.Text("\n".join(lines), Types.Text.KMD))))


def gold_card(latest: int, prev) -> CardMessage:
    delta = ""
    if prev:
        d = latest - prev
        arrow = "📈" if d > 0 else ("📉" if d < 0 else "➡️")
        delta = f"　{arrow} {d:+d}"
    text = f"**金价**　当前 `{latest:,}` 银/金{delta}"
    return CardMessage(Card(Module.Section(Element.Text(text, Types.Text.KMD))))


def leaderboard_card(guild_name: str, kind: str, ranking: list) -> CardMessage:
    title = "击杀声望榜" if kind == "pvp" else "PvE 声望榜"
    lines = [f"**{guild_name}** {title}（公会内 Top {len(ranking)}）"]
    medals = ["🥇", "🥈", "🥉"]
    for i, (name, val) in enumerate(ranking):
        prefix = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{prefix} {name}　`{fmt(val)}`")
    return CardMessage(Card(Module.Section(Element.Text("\n".join(lines), Types.Text.KMD))))
