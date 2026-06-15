"""物品名中文映射：UniqueName -> 简体中文。

数据来自 ao-bin-dumps（官方客户端导出），由 scripts/build_items.py 预处理成
data/items_zh.json 随包，运行时不拉 GitHub。查不到则回退原始 Type。
"""
import json
import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

_DEFAULT_PATH = os.path.join("data", "items_zh.json")
_MAP: Optional[dict[str, str]] = None
_BASE_ALIASES = (
    # 官方事件里弓可能是 MAIN_BOW，ao-bin-dumps 字典里同物品是 2H_BOW。
    (re.compile(r"^(T\d+)_MAIN_BOW$"), r"\1_2H_BOW"),
)
_PROTOTYPE_RE = re.compile(
    r"^T(?P<tier>\d+)_(?P<slot>HEAD|ARMOR|SHOES)_(?P<material>CLOTH|LEATHER|PLATE)_PROTOTYPE$"
)
_TIER_ZH = {
    "4": "老手级",
    "5": "专家级",
    "6": "大师级",
    "7": "宗师级",
    "8": "禅师级",
}
_PROTOTYPE_SLOT_ZH = {
    "HEAD": "头部",
    "ARMOR": "胸部",
    "SHOES": "鞋子",
}
_PROTOTYPE_MATERIAL_ZH = {
    "CLOTH": "布甲",
    "LEATHER": "皮甲",
    "PLATE": "板甲",
}


def _load(path: str = _DEFAULT_PATH) -> dict[str, str]:
    global _MAP
    if _MAP is not None:
        return _MAP
    try:
        with open(path, "r", encoding="utf-8") as f:
            _MAP = json.load(f)
    except FileNotFoundError:
        log.warning("物品字典 %s 不存在，物品名将回退为原始 Type（先跑 scripts/build_items.py）", path)
        _MAP = {}
    return _MAP


def base_name(type_: str) -> str:
    """去掉附魔后缀 @N，返回 ao-bin-dumps 的 UniqueName 基名。"""
    return type_.split("@", 1)[0]


def _alias_base_name(base: str) -> str:
    for pattern, repl in _BASE_ALIASES:
        alias = pattern.sub(repl, base)
        if alias != base:
            return alias
    return base


def _prototype_name(base: str) -> Optional[str]:
    match = _PROTOTYPE_RE.match(base)
    if not match:
        return None
    tier = _TIER_ZH.get(match.group("tier"))
    slot = _PROTOTYPE_SLOT_ZH.get(match.group("slot"))
    material = _PROTOTYPE_MATERIAL_ZH.get(match.group("material"))
    if not tier or not slot or not material:
        return None
    return f"{tier}{material}{slot}原型"


def localized(type_: str) -> str:
    """把事件里的 Type（可带 @附魔）翻成中文名；查不到回退原始 Type。"""
    if not type_:
        return type_
    m = _load()
    base = base_name(type_)
    enchant = type_.split("@", 1)[1] if "@" in type_ else ""
    name = m.get(base)
    if not name:
        name = m.get(_alias_base_name(base))
    if name:
        return f"{name}+{enchant}" if enchant and enchant != "0" else name
    # 部分特殊物品（如派系坐骑「迅爪」）UniqueName 自带 @N，基名查不到，回退整串直查
    full = m.get(type_)
    if full:
        return full
    fallback = _prototype_name(base)
    if fallback:
        return f"{fallback}+{enchant}" if enchant and enchant != "0" else fallback
    return type_


_TIER_RE = re.compile(r"^T(\d+)_")


def render_url(type_: str, quality: int = 1) -> str:
    """官方渲染图地址（KOOK 服务端会抓取并缓存到自有 CDN）。

    要换图床中转/本地缓存，只改这一个函数即可。
    """
    q = quality if quality and quality >= 1 else 1
    return f"https://render.albiononline.com/v1/item/{type_}.png?quality={q}"


def tier_enchant(type_: str) -> str:
    """从 UniqueName 提取「T层级.附魔」标注，如 T5_..@1 → `T5.1`；无层级返回空。"""
    if not type_:
        return ""
    mt = _TIER_RE.match(type_)
    if not mt:
        return ""
    tier = f"T{mt.group(1)}"
    enchant = type_.split("@", 1)[1] if "@" in type_ else ""
    return f"{tier}.{enchant}" if enchant and enchant != "0" else tier


_REVERSE: Optional[list[tuple[str, str]]] = None


def _reverse_index() -> list[tuple[str, str]]:
    """(中文名, UniqueName) 列表，供按名反查。"""
    global _REVERSE
    if _REVERSE is None:
        _REVERSE = [(zh, uniq) for uniq, zh in _load().items()]
    return _REVERSE


_UNIQUE_RE = re.compile(r"^T\d+_[A-Z0-9_@]+$", re.IGNORECASE)


def find_by_name(query: str, limit: int = 8) -> list[tuple[str, str]]:
    """按用户输入找物品，返回 [(UniqueName, 中文名), ...]。

    1) 本身就是 UniqueName（T4_...）→ 直接返回。
    2) 中文名精确匹配。
    3) 中文名子串匹配（最多 limit 条）。
    """
    q = (query or "").strip()
    if not q:
        return []
    if _UNIQUE_RE.match(q):
        return [(q.upper(), localized(q))]
    # 精确名匹配：排除 @ 附魔变体（同名只留基础款，避免误报多匹配）
    exact = [(uniq, zh) for zh, uniq in _reverse_index() if zh == q and "@" not in uniq]
    if exact:
        return exact[:limit]
    sub = [(uniq, zh) for zh, uniq in _reverse_index() if q in zh and "@" not in uniq]
    return sub[:limit]
