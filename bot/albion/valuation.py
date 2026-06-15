"""装备 + 背包估值（亚服）。

口径（见实现计划第十一节决议）：
- 主口径取红城（Caerleon）近 N 天 avg_price 的中位（走 AODP /history）。
- 红城稀疏 → 回退多城近 N 天 avg_price 的中位。
- 过滤 0 与无挂单；中位本身对离群噪音稳健。
- 不可交易物（查不到价）记 0 跳过。
- 补装总额只计穿戴装备；背包物品保留明细展示但不计入 total。
- 同品质无价时，同物品其他品质 history/current price 可按 0.85 折扣兜底。
"""
import statistics
import logging
from typing import Any

from bot.albion.market import Market, ROYAL_CITIES
from bot.albion import price_reference
from bot.store import repo

log = logging.getLogger(__name__)

SLOTS = ["MainHand", "OffHand", "Head", "Armor", "Shoes", "Bag", "Cape", "Mount", "Potion", "Food"]

# history 无成交价时回退当前挂单价（派系/Avalon/高tier 武器在亚服无历史成交但有挂单）。
# 挂单价常虚高于实际成交，按此折扣保守估。
FALLBACK_DISCOUNT = 0.85
FALLBACK_QUALITIES = (1, 2, 3, 4, 5)
REFERENCE_EXTREME_MULTIPLIER = 3.0


def _collect(victim: dict) -> list[tuple]:
    """返回 [(slot, item), ...]；装备槽 slot 为槽位名，背包件 slot=None（供展示区分核心装备）。"""
    out: list[tuple] = []
    eq = victim.get("Equipment") or {}
    for slot in SLOTS:
        it = eq.get(slot)
        if it:
            out.append((slot, it))
    for it in victim.get("Inventory") or []:
        if it:
            out.append((None, it))
    return out


def _norm_q(q: Any) -> int:
    try:
        q = int(q)
    except (TypeError, ValueError):
        return 1
    return q if q >= 1 else 1  # AODP 质量从 1 起（0/1 都算普通）


def _median_recent(data: list, days: int) -> float:
    vals = [d.get("avg_price") for d in (data or [])]
    vals = [v for v in vals if v and v > 0]
    if len(vals) > days:
        vals = vals[-days:]
    return float(statistics.median(vals)) if vals else 0.0


async def _query_history(market: Market, types: list[str], quals: list[int], days: int) -> list:
    """分块查 history，规避 URL 4096 上限。"""
    rows: list = []
    for i in range(0, len(types), 100):
        chunk = types[i : i + 100]
        data = await market.history(
            chunk, locations=ROYAL_CITIES, qualities=quals, time_scale=24
        )
        rows.extend(data or [])
    return rows


def _price_for(price: dict, type_: str, quality: int, primary: str) -> float:
    p = price.get((type_, quality, primary), 0.0)
    if p > 0:
        return p
    vals = [
        v
        for (t, q, _loc), v in price.items()
        if t == type_ and q == quality and v > 0
    ]
    return float(statistics.median(vals)) if vals else 0.0


def _other_quality_price(price: dict, type_: str, primary: str) -> float:
    vals = [
        v
        for (t, _q, loc), v in price.items()
        if t == type_ and loc == primary and v > 0
    ]
    if not vals:
        vals = [v for (t, _q, _loc), v in price.items() if t == type_ and v > 0]
    return float(statistics.median(vals)) if vals else 0.0


async def _query_prices(market: Market, types: list[str], quals: list[int]) -> dict:
    """history 拿不到价时查当前挂单 sell_price_min 兜底。返回 {(type, quality, city): sell_min}。"""
    fb: dict = {}
    for i in range(0, len(types), 100):
        chunk = types[i : i + 100]
        data = await market.prices(chunk, locations=ROYAL_CITIES, qualities=quals)
        for r in data or []:
            try:
                key = (r.get("item_id"), int(r.get("quality", 1)), r.get("city"))
            except (TypeError, ValueError):
                continue
            sp = r.get("sell_price_min") or 0
            if sp > 0:
                fb[key] = float(sp)
    return fb


def _fallback_price(fb: dict, type_: str, quality: int) -> float:
    """同质量各城 sell_min 中位（>中位 3 倍的离群剔除）；同质量无挂单则退任意质量。"""
    vals = [v for (t, q, _c), v in fb.items() if t == type_ and q == quality and v > 0]
    if not vals:
        vals = [v for (t, _q, _c), v in fb.items() if t == type_ and v > 0]
    if not vals:
        return 0.0
    med = statistics.median(vals)
    clean = [v for v in vals if v <= med * 3] or vals
    return float(statistics.median(clean))


def _reference_price(type_: str, quality: int) -> float:
    if not type_ or not price_reference.is_reference_item(type_):
        return 0.0
    ref = repo.get_price_reference(type_, quality)
    return float(ref["low_price"]) if ref else 0.0


def _cap_extreme_fallback(unit: float, reference: float) -> float:
    if reference <= 0:
        return unit
    if unit <= 0:
        return reference
    if unit > reference * REFERENCE_EXTREME_MULTIPLIER:
        return reference
    return unit


async def estimate(event_or_victim: dict, market: Market, *, days: int = 7, primary: str = "Caerleon") -> dict:
    """估一次死亡的装备+背包价值（银币）。

    入参可以是完整 event（取 Victim）或直接 victim。
    返回 {"total": int, "items": [{slot, type, quality, count, unit, value}, ...]}。
    slot 为装备槽名（背包件为 None）；history 无成交价的物品回退当前挂单价兜底。
    """
    victim = event_or_victim.get("Victim", event_or_victim)
    collected = _collect(victim)
    if not collected:
        return {"total": 0, "items": []}

    items = [it for _, it in collected]
    types = sorted({it["Type"] for it in items if it.get("Type")})
    quals = sorted({_norm_q(it.get("Quality", 1)) for it in items} | set(FALLBACK_QUALITIES))
    rows = await _query_history(market, types, quals, days)

    price: dict = {}
    for r in rows:
        try:
            key = (r.get("item_id"), int(r.get("quality", 1)), r.get("location"))
        except (TypeError, ValueError):
            continue
        price[key] = _median_recent(r.get("data"), days)

    # history 无成交价的物品（派系/Avalon/高tier 低频武器常见）→ 当前挂单价兜底
    no_hist = sorted(
        {
            it["Type"]
            for it in items
            if it.get("Type")
            and _price_for(price, it["Type"], _norm_q(it.get("Quality", 1)), primary) <= 0
        }
    )
    fb = {}
    if no_hist:
        try:
            fb = await _query_prices(market, no_hist, list(FALLBACK_QUALITIES))
        except Exception as exc:
            log.warning("当前挂单兜底查价失败，尝试数据库低价参考: %s", exc)

    breakdown: list[dict] = []
    total = 0.0
    for slot, it in collected:
        t = it.get("Type")
        q = _norm_q(it.get("Quality", 1))
        cnt = it.get("Count", 1) or 1
        ref_price = _reference_price(t, q)
        unit = _price_for(price, t, q, primary)
        if unit <= 0 and t:
            unit = _other_quality_price(price, t, primary) * FALLBACK_DISCOUNT
        if unit <= 0 and t:
            unit = _fallback_price(fb, t, q) * FALLBACK_DISCOUNT
            unit = _cap_extreme_fallback(unit, ref_price)
        if unit <= 0:
            unit = ref_price
        unit_int = int(unit)
        val = unit_int * int(cnt)
        if slot:
            total += val
        breakdown.append(
            {"slot": slot, "type": t, "quality": q, "count": cnt, "unit": unit_int, "value": val}
        )

    return {"total": int(total), "items": breakdown}


def summary(result: dict) -> dict:
    """拆分穿戴装备与背包价值。

    total 保持补装口径：只算穿戴装备；loss_total 用于播报展示完整损失。
    """
    items = result.get("items") or []
    equipment_total = sum(int(i.get("value") or 0) for i in items if i.get("slot"))
    inventory_total = sum(int(i.get("value") or 0) for i in items if not i.get("slot"))
    return {
        "equipment_total": int(equipment_total),
        "inventory_total": int(inventory_total),
        "loss_total": int(equipment_total + inventory_total),
    }
