"""给 AI 的安全事实包：只保留可解释字段，不带 Token、频道配置或 KOOK 用户明细。"""
from __future__ import annotations

from datetime import datetime, timedelta

from bot.albion import valuation

SCHEMA_VERSION = "ai.v1"


def _base(tool: str) -> dict[str, str]:
    return {"schema_version": SCHEMA_VERSION, "tool": tool}


def _time_pair(ts: object, *, source_label: str) -> dict[str, str]:
    raw = str(ts or "").strip()
    parsed = _parse_utc_time(raw)
    if not parsed:
        return {
            "raw": raw,
            "server_time_utc": f"{raw}（{source_label}，UTC 原始值）" if raw else "",
            "beijing_time_utc8": "",
            "basis": f"{source_label} UTC；北京时间 UTC+8",
        }
    return {
        "raw": raw,
        "server_time_utc": f"{parsed:%Y-%m-%d %H:%M} UTC（{source_label}）",
        "beijing_time_utc8": (
            f"{parsed + timedelta(hours=8):%Y-%m-%d %H:%M} UTC+8（北京时间）"
        ),
        "basis": f"{source_label} UTC；北京时间 UTC+8",
    }


def _parse_utc_time(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts[:19])
    except ValueError:
        return None


def _api_time(ts: object) -> dict[str, str]:
    return _time_pair(ts, source_label="服务器/API 时间")


def _database_time(ts: object) -> dict[str, str]:
    return _time_pair(ts, source_label="数据库/服务器时间")


def regear_explain_context(
    regear_row: dict, event: dict, valuation_result: dict
) -> dict:
    sums = valuation.summary(valuation_result)
    missing_items = [
        str(i.get("type"))
        for i in valuation_result.get("items", [])
        if i.get("type") and int(i.get("value") or 0) <= 0
    ]
    top_items = sorted(
        [
            {
                "slot": i.get("slot") or "Inventory",
                "type": i.get("type"),
                "value": int(i.get("value") or 0),
            }
            for i in valuation_result.get("items", [])
            if i.get("type")
        ],
        key=lambda x: x["value"],
        reverse=True,
    )[:12]
    victim = event.get("Victim") or {}
    killer = event.get("Killer") or {}
    return {
        **_base("regear_explain"),
        "request": {
            "id": regear_row.get("id"),
            "status": regear_row.get("status"),
            "est_value": int(regear_row.get("est_value") or 0),
            "event_id": regear_row.get("event_id"),
            "created_time": _database_time(regear_row.get("created_at")),
        },
        "event": {
            "event_id": event.get("EventId"),
            "time": _api_time(event.get("TimeStamp")),
            "victim_ip": victim.get("AverageItemPower"),
            "killer_name": killer.get("Name"),
            "killer_guild": killer.get("GuildName"),
            "fame": event.get("TotalVictimKillFame") or 0,
        },
        "valuation": {
            "equipment_total": sums["equipment_total"],
            "inventory_total": sums["inventory_total"],
            "loss_total": sums["loss_total"],
            "missing_items": missing_items[:12],
            "top_items": top_items,
        },
        "policy": {
            "regear_amount_basis": "only_equipped_items",
            "inventory_is_display_only": True,
            "ai_may_not_change_amount": True,
        },
    }


def regear_status_context(rows: list[dict], *, own_only: bool) -> dict:
    return {
        **_base("regear_status"),
        "scope": "own_regear_requests" if own_only else "guild_regear_requests",
        "requests": [
            {
                "id": r.get("id"),
                "status": r.get("status"),
                "est_value": int(r.get("est_value") or 0),
                "event_id": r.get("event_id"),
                "created_time": _database_time(r.get("created_at")),
                "reviewed_time": _database_time(r.get("reviewed_at")),
                "paid_time": _database_time(r.get("paid_at")),
            }
            for r in rows[:10]
        ],
    }


def battles_context(guild_name: str, battles: list[dict]) -> dict:
    return {
        **_base("battles_summary"),
        "guild_name": guild_name,
        "battles": [
            {
                "id": b.get("id") or b.get("Id") or b.get("battleId"),
                "start_time": _api_time(b.get("startTime") or b.get("StartTime")),
                "total_kills": b.get("totalKills"),
                "total_fame": b.get("totalFame"),
                "total_players": b.get("totalPlayers"),
            }
            for b in battles[:8]
        ],
    }


def binding_status_context(
    guild_binding: dict | None,
    player_binding: dict | None,
    pending_approval: dict | None,
) -> dict:
    guild = guild_binding or {}
    player = player_binding or {}
    pending = pending_approval or {}
    return {
        **_base("binding_status"),
        "guild_binding": {
            "configured": bool(guild_binding),
            "albion_guild_id": guild.get("albion_guild_id"),
            "albion_guild_name": guild.get("albion_guild_name"),
        },
        "player_binding": (
            {
                "albion_player_id": player.get("albion_player_id"),
                "albion_player_name": player.get("albion_player_name"),
                "status": player.get("status"),
                "bound_time": _database_time(player.get("bound_at")),
            }
            if player_binding
            else None
        ),
        "pending_approval": (
            {
                "id": pending.get("id"),
                "albion_player_id": pending.get("albion_player_id"),
                "albion_player_name": pending.get("albion_player_name"),
                "status": pending.get("status"),
                "created_time": _database_time(pending.get("created_at")),
            }
            if pending_approval
            else None
        ),
    }


def guild_config_context(binding: dict | None) -> dict:
    b = binding or {}
    reviewer_roles = _split_csv(b.get("regear_reviewer_role_ids"))
    trusted_roles = _split_csv(b.get("trusted_role_ids"))
    return {
        **_base("guild_config"),
        "guild_binding": {
            "configured": bool(binding),
            "albion_guild_id": b.get("albion_guild_id"),
            "albion_guild_name": b.get("albion_guild_name"),
            "created_time": _database_time(b.get("created_at")),
        },
        "settings": {
            "member_role_id": _configured_value(b.get("member_role_id")),
            "approval_channel_id": b.get("approval_channel_id"),
            "regear_channel_id": b.get("regear_channel_id"),
            "regear_apply_channel_id": b.get("regear_apply_channel_id"),
            "regear_review_channel_id": b.get("regear_review_channel_id"),
            "regear_payout_channel_id": b.get("regear_payout_channel_id"),
            "regear_notify_channel_id": b.get("regear_notify_channel_id"),
            "broadcast_channel_id": b.get("broadcast_channel_id"),
            "kill_broadcast_channel_id": b.get("kill_broadcast_channel_id"),
            "death_broadcast_channel_id": b.get("death_broadcast_channel_id"),
            "member_change_channel_id": b.get("member_change_channel_id"),
            "regear_reviewer_role_count": len(reviewer_roles),
            "trusted_role_count": len(trusted_roles),
            "kill_fame_threshold": int(b.get("kill_fame_threshold") or 100000),
        },
    }


def player_recent_activity_context(
    player: dict | None,
    kills: list[dict] | None,
    deaths: list[dict] | None,
) -> dict:
    p = player or {}
    return {
        **_base("player_recent_activity"),
        "player": {
            "id": p.get("Id") or p.get("id"),
            "name": p.get("Name") or p.get("name"),
            "guild_name": p.get("GuildName") or p.get("guildName"),
            "kill_fame": int(p.get("KillFame") or 0),
            "death_fame": int(p.get("DeathFame") or 0),
            "fame_ratio": p.get("FameRatio"),
        },
        "recent_kills": [_event_summary(e, opponent_key="Victim") for e in (kills or [])[:5]],
        "recent_deaths": [_event_summary(e, opponent_key="Killer") for e in (deaths or [])[:5]],
    }


def _configured_value(value: object) -> dict[str, object]:
    return {"configured": bool(value), "value": value or None}


def _split_csv(raw: object) -> list[str]:
    return [p.strip() for p in str(raw or "").split(",") if p.strip()]


def _event_summary(event: dict, *, opponent_key: str) -> dict:
    opponent = event.get(opponent_key) or {}
    victim = event.get("Victim") or {}
    return {
        "event_id": event.get("EventId"),
        "time": _api_time(event.get("TimeStamp")),
        "fame": int(event.get("TotalVictimKillFame") or 0),
        "opponent": {
            "name": opponent.get("Name"),
            "guild_name": opponent.get("GuildName"),
            "item_power": opponent.get("AverageItemPower"),
        },
        "victim": {
            "name": victim.get("Name"),
            "guild_name": victim.get("GuildName"),
            "item_power": victim.get("AverageItemPower"),
        },
    }
