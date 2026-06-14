"""预处理 ao-bin-dumps 物品字典 -> data/items_zh.json（UniqueName -> 简体中文）。

一次性/定期跑：python -m scripts.build_items
输出体积只含中文映射，避免运行时拉 GitHub 大文件。
"""
import json
import os
import sys

import httpx

SOURCE = "https://raw.githubusercontent.com/ao-data/ao-bin-dumps/master/formatted/items.json"
OUT = os.path.join("data", "items_zh.json")
ZH_KEYS = ("ZH-CN", "zh-CN")


def extract(raw) -> dict[str, str]:
    """兼容 list / dict 两种顶层结构，提取 UniqueName -> 中文名。"""
    items = raw.values() if isinstance(raw, dict) else raw
    out: dict[str, str] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        uniq = it.get("UniqueName")
        names = it.get("LocalizedNames") or {}
        if not uniq or not isinstance(names, dict):
            continue
        for k in ZH_KEYS:
            if names.get(k):
                out[uniq] = names[k]
                break
    return out


def main() -> int:
    print(f"下载 {SOURCE} ...")
    resp = httpx.get(SOURCE, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    raw = resp.json()
    mapping = extract(raw)
    if not mapping:
        print("未提取到任何中文名，检查源文件结构", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False)
    print(f"写入 {OUT}：{len(mapping)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
