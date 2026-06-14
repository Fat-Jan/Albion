"""ZvZ 战报聚合：参战人数、阵营统计和本会玩家高光。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


ALBIONBB_BATTLE_URL = "https://east.albionbb.com/battles/{battle_id}"


def build_battle_report(
    battle_detail: dict[str, Any],
    battle_events: list[dict[str, Any]],
    guild_name: str,
    *,
    top_limit: int = 5,
) -> dict[str, Any]:
    """把官方单场战役详情 + 击杀事件聚合成卡片可直接消费的数据。"""
    players = _as_list(_field(battle_detail, "players", "Players", default=[]))
    guild_rows = _participation_rows(
        players,
        _as_list(_field(battle_detail, "guilds", "Guilds", default=[])),
        kind="guild",
    )
    alliance_rows = _participation_rows(
        players,
        _as_list(_field(battle_detail, "alliances", "Alliances", default=[])),
        kind="alliance",
    )
    guild_row = _find_by_name(guild_rows, guild_name)
    battle_id = str(
        _field(
            battle_detail,
            "id",
            "Id",
            "albionId",
            "battleId",
            "BattleId",
            default="",
        )
    )
    return {
        "battle_id": battle_id,
        "battle_url": ALBIONBB_BATTLE_URL.format(battle_id=battle_id),
        "guild_name": guild_name,
        "start_time": _field(battle_detail, "startTime", "StartTime", "startedAt", default=""),
        "total_players": _int(
            _field(battle_detail, "totalPlayers", "TotalPlayers", default=len(players))
        ),
        "total_kills": _int(_field(battle_detail, "totalKills", "TotalKills", default=0)),
        "total_fame": _int(_field(battle_detail, "totalFame", "TotalFame", default=0)),
        "guild_players": guild_row.get("players", 0),
        "guild_kill_fame": guild_row.get("kill_fame", 0),
        "guild_row": guild_row,
        "top_guilds": guild_rows[:top_limit],
        "top_alliances": alliance_rows[:top_limit],
        "player_highlights": guild_player_highlights(players, battle_events, guild_name),
    }


def guild_player_highlights(
    players: list[dict[str, Any]],
    battle_events: list[dict[str, Any]],
    guild_name: str,
) -> dict[str, dict[str, Any] | None]:
    rows_by_id: dict[str, dict[str, Any]] = {}
    rows_by_name: dict[str, dict[str, Any]] = {}

    for player in players:
        if not _same(_field(player, "guildName", "GuildName", default=""), guild_name):
            continue
        row = {
            "name": _name(player),
            "kills": _int(_field(player, "kills", "Kills", default=0)),
            "deaths": _int(_field(player, "deaths", "Deaths", default=0)),
            "kill_fame": _int(_field(player, "killFame", "KillFame", default=0)),
            "death_fame": 0,
        }
        pid = _player_id(player)
        if pid:
            rows_by_id[pid] = row
        rows_by_name[row["name"].casefold()] = row

    for event in battle_events or []:
        victim = _field(event, "Victim", "victim", default={}) or {}
        if not _same(_field(victim, "GuildName", "guildName", default=""), guild_name):
            continue
        row = _match_player_row(victim, rows_by_id, rows_by_name)
        row["death_fame"] += _int(_field(event, "TotalVictimKillFame", default=0))

    rows = list({id(row): row for row in rows_by_name.values()}.values())
    return {
        "most_kills": _best(rows, "kills", "kill_fame"),
        "top_kill_fame": _best(rows, "kill_fame", "kills"),
        "most_deaths": _best(rows, "deaths", "death_fame"),
        "top_death_fame": _best(rows, "death_fame", "deaths"),
    }


def _participation_rows(
    players: list[dict[str, Any]], meta_rows: list[dict[str, Any]], *, kind: str
) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    meta_by_name = {_name(m).casefold(): m for m in meta_rows}
    for player in players:
        if kind == "guild":
            name = _field(player, "guildName", "GuildName", default="")
            alliance = _field(player, "allianceName", "AllianceName", default="")
        else:
            name = _field(player, "allianceName", "AllianceName", default="")
            alliance = ""
        if not name:
            continue
        key = str(name).casefold()
        row = rows.setdefault(
            key,
            {
                "name": str(name),
                "alliance": str(alliance or ""),
                "players": 0,
                "kills": 0,
                "deaths": 0,
                "kill_fame": 0,
            },
        )
        row["players"] += 1
        row["kills"] += _int(_field(player, "kills", "Kills", default=0))
        row["deaths"] += _int(_field(player, "deaths", "Deaths", default=0))
        row["kill_fame"] += _int(_field(player, "killFame", "KillFame", default=0))

    for key, meta in meta_by_name.items():
        row = rows.get(key)
        if not row:
            continue
        row["kills"] = _int(_field(meta, "kills", "Kills", default=row["kills"]))
        row["deaths"] = _int(_field(meta, "deaths", "Deaths", default=row["deaths"]))
        row["kill_fame"] = _int(
            _field(meta, "killFame", "KillFame", default=row["kill_fame"])
        )
        if kind == "guild":
            row["alliance"] = str(_field(meta, "alliance", "AllianceName", default=row["alliance"]) or "")

    return sorted(
        rows.values(),
        key=lambda r: (-r["players"], -r["kill_fame"], r["name"].casefold()),
    )


def _match_player_row(
    player: dict[str, Any],
    rows_by_id: dict[str, dict[str, Any]],
    rows_by_name: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    pid = _player_id(player)
    if pid and pid in rows_by_id:
        return rows_by_id[pid]
    name = _name(player)
    row = rows_by_name.get(name.casefold())
    if row:
        return row
    row = {
        "name": name,
        "kills": 0,
        "deaths": 0,
        "kill_fame": 0,
        "death_fame": 0,
    }
    if pid:
        rows_by_id[pid] = row
    rows_by_name[name.casefold()] = row
    return row


def _best(rows: list[dict[str, Any]], value_key: str, secondary_key: str) -> dict[str, Any] | None:
    candidates = [row for row in rows if row.get(value_key, 0) > 0]
    if not candidates:
        return None
    row = sorted(
        candidates,
        key=lambda r: (-r.get(value_key, 0), -r.get(secondary_key, 0), r["name"].casefold()),
    )[0]
    return deepcopy(row)


def _find_by_name(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for row in rows:
        if _same(row.get("name", ""), name):
            return row
    return {"name": name, "alliance": "", "players": 0, "kills": 0, "deaths": 0, "kill_fame": 0}


def _same(left: Any, right: Any) -> bool:
    return str(left or "").casefold() == str(right or "").casefold()


def _field(data: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in data:
            return data[name]
    return default


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [v for v in value.values() if isinstance(v, dict)]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _name(row: dict[str, Any]) -> str:
    return str(_field(row, "name", "Name", default="?") or "?")


def _player_id(row: dict[str, Any]) -> str:
    return str(_field(row, "id", "Id", default="") or "")
