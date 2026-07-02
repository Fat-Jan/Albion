"""Battle participation snapshots for guild attendance-style views."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def build_attendance_snapshot(
    *,
    guild_id: str,
    members: list[dict[str, Any]],
    battle_details: list[dict[str, Any]],
    min_guild_players: int = 20,
) -> dict[str, Any]:
    """Build an explainable recent battle participation snapshot.

    This is not formal CTA attendance. It only counts players from `guild_id`
    that appear in battle detail rows whose guild participation reaches the
    configured threshold.
    """
    threshold = max(1, int(min_guild_players or 20))
    member_rows = _member_rows(members)
    by_id = {row["albion_player_id"]: row for row in member_rows if row["albion_player_id"]}
    by_name = {row["name"].casefold(): row for row in member_rows if row["name"]}
    skipped: list[dict[str, Any]] = []
    counted_battles: list[dict[str, Any]] = []

    for detail in battle_details or []:
        if not isinstance(detail, dict):
            continue
        battle_id = _battle_id(detail)
        players = _as_list(_field(detail, "players", "Players", default=[]))
        guild_players = [_player_row(p) for p in players if _same(_field(p, "guildId", "GuildId"), guild_id)]
        guild_players = [p for p in guild_players if p["name"] or p["albion_player_id"]]
        if len(guild_players) < threshold:
            skipped.append(
                {
                    "battle_id": battle_id,
                    "guild_players": len(guild_players),
                    "reason": "below_min_guild_players",
                }
            )
            continue

        start_time = str(_field(detail, "startTime", "StartTime", "startedAt", default="") or "")
        counted_battles.append(
            {
                "battle_id": battle_id,
                "start_time": start_time,
                "guild_players": len(guild_players),
            }
        )
        seen_in_battle: set[str] = set()
        for player in guild_players:
            row = _match_member(player, by_id, by_name, member_rows)
            key = row["albion_player_id"] or row["name"].casefold()
            if key in seen_in_battle:
                continue
            seen_in_battle.add(key)
            row["participated_battles"] += 1
            row["kills"] += player["kills"]
            row["deaths"] += player["deaths"]
            row["kill_fame"] += player["kill_fame"]
            if _is_newer(start_time, row.get("last_seen_at")):
                row["last_seen_at"] = start_time

    counted_count = len(counted_battles)
    for row in member_rows:
        row["participation_rate"] = (
            round(row["participated_battles"] * 100 / counted_count)
            if counted_count
            else 0
        )

    ordered_members = sorted(
        member_rows,
        key=lambda r: (
            -r["participated_battles"],
            -_time_rank(str(r.get("last_seen_at") or "")),
            r["name"].casefold(),
        ),
    )
    return {
        "guild_id": guild_id,
        "battle_count": len(battle_details or []),
        "counted_battle_count": counted_count,
        "min_guild_players": threshold,
        "members": ordered_members,
        "battles": counted_battles,
        "skipped_battles": skipped,
    }


def _member_rows(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    seen: set[str] = set()
    for member in members or []:
        if not isinstance(member, dict):
            continue
        player_id = str(_field(member, "Id", "id", "playerId", "PlayerId", default="") or "")
        name = str(_field(member, "Name", "name", default="") or "")
        key = player_id or name.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "albion_player_id": player_id,
                "name": name,
                "participated_battles": 0,
                "participation_rate": 0,
                "last_seen_at": "",
                "kills": 0,
                "deaths": 0,
                "kill_fame": 0,
            }
        )
    return rows


def _player_row(player: dict[str, Any]) -> dict[str, Any]:
    return {
        "albion_player_id": str(_field(player, "id", "Id", "playerId", "PlayerId", default="") or ""),
        "name": str(_field(player, "name", "Name", default="") or ""),
        "kills": _int(_field(player, "kills", "Kills", default=0)),
        "deaths": _int(_field(player, "deaths", "Deaths", default=0)),
        "kill_fame": _int(_field(player, "killFame", "KillFame", default=0)),
    }


def _match_member(
    player: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    by_name: dict[str, dict[str, Any]],
    members: list[dict[str, Any]],
) -> dict[str, Any]:
    player_id = player["albion_player_id"]
    if player_id and player_id in by_id:
        return by_id[player_id]
    name_key = player["name"].casefold()
    if name_key and name_key in by_name:
        return by_name[name_key]
    row = {
        "albion_player_id": player_id,
        "name": player["name"],
        "participated_battles": 0,
        "participation_rate": 0,
        "last_seen_at": "",
        "kills": 0,
        "deaths": 0,
        "kill_fame": 0,
    }
    members.append(row)
    if player_id:
        by_id[player_id] = row
    if name_key:
        by_name[name_key] = row
    return row


def _battle_id(detail: dict[str, Any]) -> str:
    return str(
        _field(detail, "id", "Id", "albionId", "battleId", "BattleId", default="")
        or ""
    )


def _field(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if isinstance(row, dict) and key in row:
            return row.get(key)
    return default


def _as_list(value: Any) -> list:
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return value
    return []


def _same(left: Any, right: Any) -> bool:
    return str(left or "").casefold() == str(right or "").casefold()


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_newer(candidate: str, current: str | None) -> bool:
    if not candidate:
        return False
    if not current:
        return True
    return _time_rank(candidate) > _time_rank(current)


def _time_rank(value: str) -> float:
    if not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()
