"""Runtime seed data for known KOOK guild deployments."""
from __future__ import annotations

import logging
from typing import Any

from bot.store import repo

log = logging.getLogger(__name__)

RUNTIME_GUILD_CONFIGS: dict[str, dict[str, Any]] = {
    "eu": {
        "kook_guild_id": "4676167053713576",
        "albion_guild_id": "7tmt12sOTkGgcqZL3jSy7Q",
        "albion_guild_name": "Top Squad",
        "member_role_id": None,
        "approval_channel_id": "6593832141020317",
        "regear_apply_channel_id": "1796790216225633",
        "regear_review_channel_id": "6148000249978208",
        "regear_payout_channel_id": "5305586332660592",
        "regear_notify_channel_id": "9949355172393396",
        "broadcast_channel_id": None,
        "kill_broadcast_channel_id": "8415323442916410",
        "death_broadcast_channel_id": "3162690807846766",
        "battle_report_channel_id": "7532177792027984",
        "battle_report_min_guild_players": 20,
        "member_change_channel_id": "3626370873673494",
        "regear_reviewer_role_ids": None,
        "trusted_role_ids": None,
        "kill_fame_threshold": 100000,
        "created_by": "setup-fumass",
    },
    "asia": {
        "kook_guild_id": "4676167053713576",
        "albion_guild_id": "KVO3_vrITECLAIRl1juHSg",
        "albion_guild_name": "Mika",
        "member_role_id": "47139243",
        "approval_channel_id": "6280501542155342",
        "regear_apply_channel_id": "8092855830265715",
        "regear_review_channel_id": "2772001930672157",
        "regear_payout_channel_id": "9380523626852434",
        "regear_notify_channel_id": "9980001624642186",
        "broadcast_channel_id": None,
        "kill_broadcast_channel_id": "4326560318750543",
        "death_broadcast_channel_id": "5193310241387334",
        "battle_report_channel_id": "3891092612097998",
        "battle_report_min_guild_players": 20,
        "member_change_channel_id": "1203064556541945",
        "regear_reviewer_role_ids": None,
        "trusted_role_ids": None,
        "kill_fame_threshold": 400000,
        "created_by": "1380312587",
    },
}

SETTING_KEYS = tuple(sorted(repo.SETTING_FIELDS))


def seed_runtime_guild_config(region_code: str) -> dict[str, Any] | None:
    """Seed the configured runtime guild binding for the active region."""
    normalized = _normalize_region(region_code)
    cfg = RUNTIME_GUILD_CONFIGS.get(normalized)
    if cfg is None:
        log.warning("no runtime guild config for region=%s; skip seed", normalized)
        return None

    kook_guild_id = cfg["kook_guild_id"]
    existing = repo.get_guild_binding(kook_guild_id, normalized)
    force_settings = (
        existing is None
        or existing.get("albion_guild_id") != cfg["albion_guild_id"]
        or existing.get("albion_guild_name") != cfg["albion_guild_name"]
    )
    repo.bind_guild(
        kook_guild_id,
        normalized,
        cfg["albion_guild_id"],
        cfg["albion_guild_name"],
        cfg["created_by"],
    )
    current = repo.get_guild_binding(kook_guild_id, normalized) or {}
    for key in SETTING_KEYS:
        if key in cfg:
            if not force_settings and current.get(key) not in (None, ""):
                continue
            repo.set_setting(kook_guild_id, normalized, key, cfg[key])

    log.info(
        "seeded runtime guild config region=%s kook_guild_id=%s albion_guild=%s/%s setting_keys=%s",
        normalized,
        kook_guild_id,
        cfg["albion_guild_name"],
        cfg["albion_guild_id"],
        sum(1 for key in SETTING_KEYS if key in cfg),
    )
    return dict(cfg)


def _normalize_region(region_code: str) -> str:
    text = str(region_code or "").strip().lower()
    if text in {"eu", "europe", "ams", "live_ams"}:
        return "eu"
    if text in {"asia", "as", "east", "sgp", "live_sgp"}:
        return "asia"
    return text
