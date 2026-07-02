"""区服频道作用域：让双 bot 只响应自己前缀的 KOOK 频道。"""
from __future__ import annotations

from datetime import UTC, datetime
import logging

from bot import config
from bot.store import repo

CHANNEL_CUTOFF = datetime(2026, 6, 1, tzinfo=UTC)
REGION_PREFIXES = ("eu", "asia")
CHANNEL_SETTING_FIELDS = (
    "approval_channel_id",
    "regear_channel_id",
    "regear_apply_channel_id",
    "regear_review_channel_id",
    "regear_payout_channel_id",
    "regear_notify_channel_id",
    "broadcast_channel_id",
    "kill_broadcast_channel_id",
    "death_broadcast_channel_id",
    "battle_report_channel_id",
    "member_change_channel_id",
)

log = logging.getLogger(__name__)


def region_code() -> str:
    """Deprecated compatibility shim; new code should pass region explicitly."""
    return config.DEFAULT_REGION_CODE


def scoped_name(name: str, *, region: str | None = None) -> str:
    base = str(name or "").strip()
    prefix = f"{_resolve_region(region)}-"
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


def channel_name_matches_region(name: str | None, *, region: str | None = None) -> bool:
    return str(name or "").strip().lower().startswith(f"{_resolve_region(region)}-")


def channel_matches_region(channel, *, region: str | None = None) -> bool:
    return channel_name_matches_region(getattr(channel, "name", None), region=region)


def channel_allowed(
    channel,
    *,
    allow_bootstrap: bool = False,
    region: str | None = None,
    binding: dict | None = None,
) -> bool:
    if channel_matches_region(channel, region=region):
        return True
    name = getattr(channel, "name", None)
    if has_known_region_prefix(name):
        return False
    if channel_id_in_binding(
        binding, getattr(channel, "id", None), CHANNEL_SETTING_FIELDS
    ):
        return True
    return False


def is_other_region_channel(
    channel, cfg: config.AlbionRegionConfig | None = None, *, region: str | None = None
) -> bool:
    current_region = region
    if current_region is None and cfg is not None:
        current_region = getattr(cfg, "region_code", None) or getattr(cfg, "region", None)
    current_region = _resolve_region(current_region)
    other_regions = tuple(prefix for prefix in REGION_PREFIXES if prefix != current_region)
    name = str(getattr(channel, "name", "") or "").strip().lower()
    return any(name.startswith(f"{prefix}-") for prefix in other_regions)


def should_process_message(
    msg, *, allow_bootstrap: bool = False, region: str | None = None
) -> bool:
    channel = getattr(getattr(msg, "ctx", None), "channel", None)
    resolved_region = region or _message_region(msg)
    if channel_allowed(channel, allow_bootstrap=allow_bootstrap, region=resolved_region):
        return True
    binding = _message_binding(msg, resolved_region)
    return channel_allowed(
        channel,
        allow_bootstrap=allow_bootstrap,
        region=resolved_region,
        binding=binding,
    )


def is_channel_created_in_scope(channel) -> bool:
    created_at = _parse_created_at(getattr(channel, "created_at", None))
    if created_at is None:
        return False
    return created_at >= CHANNEL_CUTOFF


def is_reusable_region_channel(channel, *, region: str | None = None) -> bool:
    if not channel_matches_region(channel, region=region):
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
    *,
    region: str | None = None,
) -> bool:
    if not channel_id_in_binding(binding, channel_id, fields):
        return False
    if channel_matches_region(channel, region=region):
        return True
    return not has_known_region_prefix(getattr(channel, "name", None))


def _resolve_region(region: str | None = None) -> str:
    if region:
        return _normalize_region(region)
    return region_code()


def _message_region(msg) -> str | None:
    ctx = getattr(msg, "ctx", None)
    bot = getattr(ctx, "bot", None) or getattr(msg, "bot", None)
    raw = getattr(bot, "_region", None) or getattr(bot, "region", None)
    if raw:
        return _normalize_region(raw)
    return None


def _message_binding(msg, region: str | None) -> dict | None:
    guild_id = _message_guild_id(msg)
    if not guild_id:
        return None
    try:
        return repo.get_guild_binding(str(guild_id), _resolve_region(region))
    except Exception as exc:
        log.warning(
            "load guild binding for region scope failed guild=%s: %s",
            guild_id,
            exc,
        )
        return None


def _message_guild_id(msg) -> str | None:
    ctx = getattr(msg, "ctx", None)
    guild = getattr(ctx, "guild", None)
    for candidate in (
        getattr(guild, "id", None),
        getattr(ctx, "guild_id", None),
        getattr(msg, "guild_id", None),
    ):
        if candidate:
            return str(candidate)
    return None


def _normalize_region(raw: str) -> str:
    text = str(raw or "").strip().lower()
    if text in {"eu", "europe", "ams", "live_ams"}:
        return "eu"
    if text in {"asia", "as", "east", "sgp", "live_sgp"}:
        return "asia"
    return text


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
