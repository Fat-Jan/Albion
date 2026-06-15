"""审计装备类物品中文名覆盖率。

全量装备类清单来自 ao-bin-dumps；实时漏网别名来自 gameinfo 近期事件。
运行示例：
    python -m scripts.audit_item_localization --event-pages 20
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable

import httpx

from bot import config
from bot.albion import items
from scripts import build_items

DEFAULT_OUT_DIR = Path("data/reports")
EVENT_PAGE_SIZE = 51
GEAR_CATEGORY_ORDER = (
    "mainhand",
    "offhand",
    "armor",
    "bag",
    "cape",
    "mount",
    "food",
    "potion",
)


def _base_item_id(item_id: str) -> str:
    return (item_id or "").split("@", 1)[0]


def gear_category(item_id: str) -> str | None:
    """返回播报/补装会展示的装备类目；非装备类返回 None。"""
    base = _base_item_id(item_id)
    if re.match(r"^T\d+_MAIN_", base):
        return "mainhand"
    if re.match(r"^T\d+_2H_", base) and not re.match(r"^T\d+_2H_TOOL_", base):
        return "mainhand"
    if re.match(r"^T\d+_OFF_", base):
        return "offhand"
    if re.match(r"^T\d+_(HEAD|ARMOR|SHOES)_", base):
        return "armor"
    if re.match(r"^T\d+_BAG", base):
        return "bag"
    if re.match(r"^T\d+_(CAPE|CAPEITEM_)", base):
        return "cape"
    if re.match(r"^T\d+_MOUNT_", base):
        return "mount"
    if re.match(r"^T\d+_MEAL_", base):
        return "food"
    if re.match(r"^T\d+_POTION_", base):
        return "potion"
    return None


def _zh_name(record: dict[str, Any]) -> str:
    names = record.get("LocalizedNames") or {}
    if not isinstance(names, dict):
        return ""
    for key in build_items.ZH_KEYS:
        name = names.get(key)
        if name:
            return name
    return ""


def _iter_source_records(raw: Any) -> Iterable[dict[str, Any]]:
    values = raw.values() if isinstance(raw, dict) else raw
    for record in values or []:
        if isinstance(record, dict):
            yield record


def source_gear_records(raw: Any) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for record in _iter_source_records(raw):
        item_id = record.get("UniqueName")
        if not isinstance(item_id, str):
            continue
        category = gear_category(item_id)
        if not category:
            continue
        records.append({"item_id": item_id, "category": category, "zh": _zh_name(record)})
    return records


def _iter_type_values(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "Type" and isinstance(child, str) and gear_category(child):
                yield child
            else:
                yield from _iter_type_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_type_values(child)


def collect_event_item_ids(event: dict[str, Any]) -> set[str]:
    """收集 event 里装备、背包、食物、药水等装备类 Type。"""
    return set(_iter_type_values(event))


def runtime_missing_ids(
    item_ids: Iterable[str], localize: Callable[[str], str] = items.localized
) -> list[str]:
    missing = []
    for item_id in sorted(set(item_ids)):
        localized = localize(item_id)
        if not localized or localized == item_id:
            missing.append(item_id)
    return missing


def _load_json_file(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _fetch_json(url: str, *, params: dict[str, Any] | None = None, timeout: int = 60) -> Any:
    resp = httpx.get(url, params=params, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


def fetch_recent_events(pages: int, *, base_url: str = config.GAMEINFO_BASE) -> list[dict]:
    events: list[dict] = []
    pages = max(0, int(pages))
    for page in range(pages):
        try:
            rows = _fetch_json(
                base_url.rstrip("/") + "/events",
                params={"limit": EVENT_PAGE_SIZE, "offset": page * EVENT_PAGE_SIZE},
                timeout=30,
            )
        except httpx.HTTPStatusError as exc:
            if events and exc.response.status_code == 400:
                break
            raise
        if not rows:
            break
        events.extend(row for row in rows if isinstance(row, dict))
        if len(rows) < EVENT_PAGE_SIZE:
            break
    return events


def _category_counts(item_ids: Iterable[str]) -> dict[str, int]:
    counts = Counter(gear_category(item_id) for item_id in item_ids)
    return {cat: counts.get(cat, 0) for cat in GEAR_CATEGORY_ORDER}


def _raw_local_missing(item_id: str, local_map: dict[str, str]) -> bool:
    return item_id not in local_map and _base_item_id(item_id) not in local_map


def build_audit(
    source_raw: Any,
    local_map: dict[str, str],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    source_records = source_gear_records(source_raw)
    source_ids = [r["item_id"] for r in source_records]
    source_missing_zh = sorted(r["item_id"] for r in source_records if not r["zh"])
    local_missing_source_zh = sorted(
        r["item_id"] for r in source_records if r["zh"] and r["item_id"] not in local_map
    )
    source_runtime_missing = runtime_missing_ids(source_ids)

    event_counter: Counter[str] = Counter()
    for event in events:
        event_counter.update(collect_event_item_ids(event))
    event_ids = sorted(event_counter)
    event_missing_runtime = runtime_missing_ids(event_ids)
    event_raw_missing = sorted(
        item_id for item_id in event_ids if _raw_local_missing(item_id, local_map)
    )
    event_alias_covered = sorted(set(event_raw_missing) - set(event_missing_runtime))

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": {
            "url": build_items.SOURCE,
            "gear_items": len(source_ids),
            "category_counts": _category_counts(source_ids),
            "missing_zh_count": len(source_missing_zh),
            "missing_zh": source_missing_zh,
            "local_missing_source_zh_count": len(local_missing_source_zh),
            "local_missing_source_zh": local_missing_source_zh,
            "runtime_missing_count": len(source_runtime_missing),
            "runtime_missing": source_runtime_missing,
        },
        "events": {
            "scanned_events": len(events),
            "unique_item_ids": len(event_ids),
            "category_counts": _category_counts(event_ids),
            "raw_missing_local_count": len(event_raw_missing),
            "raw_missing_local": event_raw_missing,
            "alias_covered_count": len(event_alias_covered),
            "alias_covered": event_alias_covered,
            "runtime_missing_count": len(event_missing_runtime),
            "runtime_missing": event_missing_runtime,
            "top_items": event_counter.most_common(50),
        },
    }


def _markdown_list(values: list[str], limit: int = 80) -> str:
    if not values:
        return "- 无\n"
    shown = values[:limit]
    lines = [f"- `{value}`" for value in shown]
    if len(values) > limit:
        lines.append(f"- ... 另有 {len(values) - limit} 条")
    return "\n".join(lines) + "\n"


def write_reports(audit: dict[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = out_dir / f"item-localization-audit-{stamp}.json"
    md_path = out_dir / f"item-localization-audit-{stamp}.md"

    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    source = audit["source"]
    events = audit["events"]
    md = [
        "# Item Localization Audit",
        "",
        f"- generated_at: `{audit['generated_at']}`",
        f"- source_gear_items: `{source['gear_items']}`",
        f"- source_missing_zh: `{source['missing_zh_count']}`",
        f"- local_missing_source_zh: `{source['local_missing_source_zh_count']}`",
        f"- source_runtime_missing: `{source['runtime_missing_count']}`",
        f"- scanned_events: `{events['scanned_events']}`",
        f"- event_unique_item_ids: `{events['unique_item_ids']}`",
        f"- event_raw_missing_local: `{events['raw_missing_local_count']}`",
        f"- event_alias_covered: `{events['alias_covered_count']}`",
        f"- event_runtime_missing: `{events['runtime_missing_count']}`",
        "",
        "## Source Category Counts",
        "",
    ]
    for cat, count in source["category_counts"].items():
        md.append(f"- {cat}: `{count}`")
    md.extend(["", "## Event Category Counts", ""])
    for cat, count in events["category_counts"].items():
        md.append(f"- {cat}: `{count}`")
    md.extend(["", "## Runtime Missing From Recent Events", ""])
    md.append(_markdown_list(events["runtime_missing"]))
    md.extend(["", "## Raw Missing But Covered By Runtime Alias", ""])
    md.append(_markdown_list(events["alias_covered"]))
    md.extend(["", "## Source Items Without Chinese Name", ""])
    md.append(_markdown_list(source["missing_zh"]))
    md.extend(["", "## Source Chinese Names Missing Locally", ""])
    md.append(_markdown_list(source["local_missing_source_zh"]))
    md.extend(["", "## Source Runtime Missing", ""])
    md.append(_markdown_list(source["runtime_missing"]))
    md_path.write_text("\n".join(md), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-pages", type=int, default=20, help="扫描 gameinfo /events 页数")
    parser.add_argument("--source-file", help="使用本地 ao-bin-dumps items.json，跳过下载源文件")
    parser.add_argument("--events-file", help="使用本地 events JSON，跳过 gameinfo 请求")
    parser.add_argument("--local-map", default=build_items.OUT, help="本地 items_zh.json 路径")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="报告输出目录")
    parser.add_argument("--fail-on-missing", action="store_true", help="存在运行时缺失时返回非 0")
    args = parser.parse_args()

    source_raw = (
        _load_json_file(args.source_file)
        if args.source_file
        else _fetch_json(build_items.SOURCE, timeout=60)
    )
    events = (
        _load_json_file(args.events_file)
        if args.events_file
        else fetch_recent_events(args.event_pages)
    )
    local_map = _load_json_file(args.local_map)

    audit = build_audit(source_raw, local_map, events)
    json_path, md_path = write_reports(audit, Path(args.out_dir))

    print(f"报告 JSON: {json_path}")
    print(f"报告 Markdown: {md_path}")
    print(
        "全量装备类 {gear}；源缺中文 {src_missing}；本地漏同步 {local_missing}；"
        "全量运行时缺中文 {source_runtime_missing}；近期事件物品 {event_ids}；"
        "近期运行时缺中文 {runtime_missing}；别名兜底 {alias_covered}".format(
            gear=audit["source"]["gear_items"],
            src_missing=audit["source"]["missing_zh_count"],
            local_missing=audit["source"]["local_missing_source_zh_count"],
            source_runtime_missing=audit["source"]["runtime_missing_count"],
            event_ids=audit["events"]["unique_item_ids"],
            runtime_missing=audit["events"]["runtime_missing_count"],
            alias_covered=audit["events"]["alias_covered_count"],
        )
    )
    if args.fail_on_missing and audit["events"]["runtime_missing_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
