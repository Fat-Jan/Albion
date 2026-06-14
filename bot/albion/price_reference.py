"""武器/副手市场低价参考。

实时估价仍优先使用 history 与当前挂单；这里维护一份 T4-T8 主手/双手/副手
低价快照，在 AODP 某些武器无成交或临时查价失败时兜底。
"""
import re
import statistics
from typing import Iterable

from bot.albion import items
from bot.albion.market import Market, ROYAL_CITIES
from bot.store import repo

REF_QUALITIES = (1, 2, 3, 4, 5)
REF_ENCHANTS = ("", "@1", "@2", "@3", "@4")
REF_BATCH_SIZE = 60
REF_REFRESH_INTERVAL_MIN = 60 * 24 * 3

_TIER_RE = re.compile(r"^T(\d+)_(.+)$")


def _base_item_id(item_id: str) -> str:
    return (item_id or "").split("@", 1)[0]


def _tier(item_id: str) -> int | None:
    m = _TIER_RE.match(_base_item_id(item_id))
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def slot_group(item_id: str) -> str | None:
    base = _base_item_id(item_id)
    if re.match(r"^T\d+_OFF_", base):
        return "offhand"
    if re.match(r"^T\d+_MAIN_", base):
        return "mainhand"
    if re.match(r"^T\d+_2H_", base) and not re.match(r"^T\d+_2H_TOOL_", base):
        return "mainhand"
    return None


def is_reference_item(item_id: str) -> bool:
    tier = _tier(item_id)
    return tier is not None and 4 <= tier <= 8 and slot_group(item_id) is not None


def expand_enchants(item_ids: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item_id in item_ids:
        base = _base_item_id(item_id)
        if not is_reference_item(base):
            continue
        for suffix in REF_ENCHANTS:
            expanded = f"{base}{suffix}"
            if expanded not in seen:
                seen.add(expanded)
                out.append(expanded)
    return out


def all_reference_item_ids() -> list[str]:
    base_ids = sorted({item_id for item_id in items._load().keys() if is_reference_item(item_id)})
    return expand_enchants(base_ids)


def _low_price(values: list[int]) -> int:
    vals = [int(v) for v in values if v and int(v) > 0]
    if not vals:
        return 0
    med = statistics.median(vals)
    clean = [v for v in vals if v <= med * 3] or vals
    return min(clean)


def _records_from_price_rows(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, int], list[int]] = {}
    for row in rows or []:
        item_id = row.get("item_id")
        if not is_reference_item(item_id):
            continue
        try:
            quality = int(row.get("quality", 1))
            sell_min = int(row.get("sell_price_min") or 0)
        except (TypeError, ValueError):
            continue
        if quality < 1 or sell_min <= 0:
            continue
        grouped.setdefault((item_id, quality), []).append(sell_min)

    records: list[dict] = []
    for (item_id, quality), values in grouped.items():
        price = _low_price(values)
        group = slot_group(item_id)
        if not price or not group:
            continue
        records.append(
            {
                "item_id": item_id,
                "quality": quality,
                "slot_group": group,
                "low_price": price,
                "sample_count": len(values),
                "source": "aodp_prices_sell_min",
            }
        )
    return records


async def refresh_weapon_price_reference(
    market: Market,
    *,
    item_ids: Iterable[str] | None = None,
    qualities: Iterable[int] = REF_QUALITIES,
    batch_size: int = REF_BATCH_SIZE,
) -> dict:
    expanded = expand_enchants(item_ids) if item_ids is not None else all_reference_item_ids()
    quals = tuple(sorted({int(q) for q in qualities if int(q) > 0}))
    stats = {"items": len(expanded), "api_rows": 0, "records": 0}
    if not expanded or not quals:
        return stats

    batch_size = max(1, int(batch_size or REF_BATCH_SIZE))
    for i in range(0, len(expanded), batch_size):
        chunk = expanded[i : i + batch_size]
        rows = await market.prices(chunk, locations=ROYAL_CITIES, qualities=quals)
        stats["api_rows"] += len(rows or [])
        records = _records_from_price_rows(rows or [])
        stats["records"] += repo.upsert_price_references(records)
    return stats
