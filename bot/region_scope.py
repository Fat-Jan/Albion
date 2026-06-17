"""区服频道作用域：让双 bot 只响应自己前缀的 KOOK 频道。"""
from __future__ import annotations

import os
from datetime import UTC, datetime

from bot import config

CHANNEL_CUTOFF = datetime(2026, 6, 1, tzinfo=UTC)
REGION_PREFIXES = ("eu", "asia")


def region_code() -> str:
    raw = os.getenv("KOOK_REGION_CODE", "").strip().lower()
    if raw:
        return _normalize_region(raw)
    return _infer_region_from_config()


def scoped_name(name: str) -> str:
    base = str(name or "").strip()
    prefix = f"{region_code()}-"
    if base.startswith(prefix):
        return base
    return f"{prefix}{strip_known_prefix(base)}"


def strip_known_prefix(name: str) -> str:
    text = str(name or "").strip()
    for prefix in REGION_PREFIXES:
        marker = f"{prefix}-"
        if text.lower().startswith(marker):
            return text[len(marker) :]
    return text


def channel_name_matches_region(name: str | None) -> bool:
    return str(name or "").strip().lower().startswith(f"{region_code()}-")


def channel_matches_region(channel) -> bool:
    return channel_name_matches_region(getattr(channel, "name", None))


def channel_allowed(channel, *, allow_bootstrap: bool = False) -> bool:
    if channel_matches_region(channel):
        return True
    return False


def should_process_message(msg, *, allow_bootstrap: bool = False) -> bool:
    channel = getattr(getattr(msg, "ctx", None), "channel", None)
    return channel_allowed(channel, allow_bootstrap=allow_bootstrap)


def is_channel_created_in_scope(channel) -> bool:
    created_at = _parse_created_at(getattr(channel, "created_at", None))
    if created_at is None:
        return False
    return created_at >= CHANNEL_CUTOFF


def is_reusable_region_channel(channel) -> bool:
    if not channel_matches_region(channel):
        return False
    created_at = _parse_created_at(getattr(channel, "created_at", None))
    return created_at is None or created_at >= CHANNEL_CUTOFF


def has_known_region_prefix(name: str | None) -> bool:
    text = str(name or "").strip().lower()
    return any(text.startswith(f"{prefix}-") for prefix in REGION_PREFIXES)


def channel_id_in_binding(binding: dict | None, channel_id: object, fields: tuple[str, ...]) -> bool:
    cid = str(channel_id or "")
    if not binding or not cid:
        return False
    return any(str(binding.get(field) or "") == cid for field in fields)


def configured_channel_matches_region(
    binding: dict | None,
    channel_id: object,
    fields: tuple[str, ...],
    channel,
) -> bool:
    if not channel_id_in_binding(binding, channel_id, fields):
        return False
    if channel_matches_region(channel):
        return True
    return getattr(channel, "name", None) is None


def _normalize_region(raw: str) -> str:
    text = str(raw or "").strip().lower()
    if text in {"eu", "europe", "ams", "live_ams"}:
        return "eu"
    if text in {"asia", "as", "east", "sgp", "live_sgp"}:
        return "asia"
    return text


def _infer_region_from_config() -> str:
    probes = " ".join(
        (
            config.GAMEINFO_BASE,
            config.AODP_BASE,
            config.ALBIONBB_BASE,
            config.ALBIONBB_WEB_BASE,
            config.KILLBOARD_SERVER,
        )
    ).lower()
    if any(token in probes for token in ("gameinfo-sgp", "/asia", "east.", "live_sgp")):
        return "asia"
    return "eu"


def _parse_created_at(raw) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, (int, float)):
        value = float(raw)
        if value > 10_000_000_000:
            value /= 1000
        dt = datetime.fromtimestamp(value, tz=UTC)
    else:
        text = str(raw).strip()
        if not text:
            return None
        if text.isdigit():
            return _parse_created_at(int(text))
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
