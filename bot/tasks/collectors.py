"""Low-frequency read-only data collectors for cached dashboards."""
from __future__ import annotations

import logging
from typing import Any

from bot.store import repo

log = logging.getLogger(__name__)


async def collect_guild_members_once(gi, guild_binding: dict[str, Any]) -> dict[str, Any]:
    kook_guild_id = str(guild_binding["kook_guild_id"])
    region = str(guild_binding.get("region") or "eu")
    albion_guild_id = str(guild_binding["albion_guild_id"])
    try:
        members = await gi.guild_members(albion_guild_id)
        captured_at = repo.save_guild_member_snapshot(
            kook_guild_id,
            region,
            albion_guild_id,
            members or [],
        )
        repo.mark_collector_run("guild_members", kook_guild_id, region)
        return {
            "members": len(members or []),
            "captured_at": captured_at,
            "errors": 0,
        }
    except Exception as exc:
        repo.mark_collector_run(
            "guild_members",
            kook_guild_id,
            region,
            status="error",
            error=str(exc)[:500],
        )
        raise


async def collect_recent_battles_once(
    gi,
    guild_binding: dict[str, Any],
    *,
    limit: int = 20,
) -> dict[str, Any]:
    kook_guild_id = str(guild_binding["kook_guild_id"])
    region = str(guild_binding.get("region") or "eu")
    albion_guild_id = str(guild_binding["albion_guild_id"])
    try:
        battle_rows = await gi.battles(guild_id=albion_guild_id, limit=limit)
    except Exception as exc:
        repo.mark_collector_run(
            "attendance_battles",
            kook_guild_id,
            region,
            status="error",
            error=str(exc)[:500],
        )
        raise

    stored = 0
    errors = 0
    seen_ids: set[str] = set()
    for row in battle_rows or []:
        battle_id = _battle_id(row) if isinstance(row, dict) else ""
        if not battle_id or battle_id in seen_ids:
            continue
        seen_ids.add(battle_id)
        try:
            detail = await gi.battle(battle_id)
            repo.store_battle_detail(kook_guild_id, region, albion_guild_id, detail)
            stored += 1
        except Exception as exc:
            errors += 1
            log.warning("出勤采集 battle detail 失败 battle=%s: %s", battle_id, exc)
            continue
    repo.mark_collector_run(
        "attendance_battles",
        kook_guild_id,
        region,
        status="partial" if errors else "ok",
        error=f"{errors} battle detail failures" if errors else None,
    )
    return {
        "candidates": len(battle_rows or []),
        "stored": stored,
        "errors": errors,
    }


async def collect_high_fame_events_once(
    gi,
    guild_binding: dict[str, Any],
    *,
    limit: int = 51,
    fame_threshold: int = 1_000_000,
) -> dict[str, Any]:
    kook_guild_id = str(guild_binding["kook_guild_id"])
    region = str(guild_binding.get("region") or "eu")
    albion_guild_id = str(guild_binding["albion_guild_id"])
    try:
        events = await gi.events(limit=limit, offset=0)
        stored = repo.save_high_fame_events(
            kook_guild_id,
            region,
            albion_guild_id,
            events or [],
            min_fame=fame_threshold,
        )
        repo.mark_collector_run("high_fame_events", kook_guild_id, region)
        return {
            "candidates": len(events or []),
            "stored": stored,
            "errors": 0,
        }
    except Exception as exc:
        repo.mark_collector_run(
            "high_fame_events",
            kook_guild_id,
            region,
            status="error",
            error=str(exc)[:500],
        )
        raise


async def collect_fame_leaderboards_once(
    gi,
    guild_binding: dict[str, Any] | None = None,
    *,
    region: str = "eu",
    limit: int = 20,
) -> dict[str, Any]:
    kook_guild_id = str((guild_binding or {}).get("kook_guild_id") or "global")
    region = str((guild_binding or {}).get("region") or region)
    try:
        snapshots = {
            "player_pvp_week": await gi.player_statistics("PvP", "week", limit=limit),
            "player_pve_week": await gi.player_statistics("PvE", "week", limit=limit),
            "player_fame_week": await gi.player_fame("week", limit=limit),
            "guild_fame_week": await gi.guild_fame("week", limit=limit),
        }
        for kind, payload in snapshots.items():
            repo.save_leaderboard_snapshot(kind, payload or [], kook_guild_id=kook_guild_id)
        repo.mark_collector_run("leaderboards", kook_guild_id, region)
        return {
            "snapshots": len(snapshots),
            "items": sum(len(payload or []) for payload in snapshots.values()),
            "errors": 0,
        }
    except Exception as exc:
        repo.mark_collector_run(
            "leaderboards",
            kook_guild_id,
            region,
            status="error",
            error=str(exc)[:500],
        )
        raise


async def collect_gold_price_once(market, *, region: str = "eu", count: int = 24) -> dict[str, Any]:
    try:
        rows = await market.gold(count=count)
        captured_at = repo.save_gold_price_snapshot(rows or [])
        repo.mark_collector_run("gold_price", "global", region)
        return {
            "rows": len(rows or []),
            "captured_at": captured_at,
            "errors": 0,
        }
    except Exception as exc:
        repo.mark_collector_run(
            "gold_price",
            "global",
            region,
            status="error",
            error=str(exc)[:500],
        )
        raise


def _battle_id(row: dict[str, Any]) -> str:
    for key in ("id", "Id", "albionId", "battleId", "BattleId"):
        value = row.get(key)
        if value:
            return str(value)
    return ""
