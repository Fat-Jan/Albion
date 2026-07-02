"""绑定关系读写。低频小数据，每次开短连接即可。"""
import json
from datetime import UTC, datetime
from typing import Any
from typing import Optional

from bot.albion.attendance import build_attendance_snapshot
from bot.store.db import get_conn

DEFAULT_REGION = "eu"
_MISSING = object()


def _is_region(value: Any) -> bool:
    return str(value or "").strip().lower() in {"eu", "asia"}

# 允许 /设置 写入的字段白名单
SETTING_FIELDS = {
    "member_role_id",
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
    "battle_report_min_guild_players",
    "member_change_channel_id",
    "regear_reviewer_role_ids",
    "trusted_role_ids",
    "kill_fame_threshold",
}


def bind_guild(
    kook_guild_id: str,
    region: str,
    albion_guild_id: str | None = None,
    albion_guild_name: str | None = None,
    created_by: str | None = None,
) -> None:
    """绑定/改绑公会（同一 KOOK 服务器只留一条，冲突即覆盖核心字段，保留已有设置）。"""
    if created_by is None:
        region, albion_guild_id, albion_guild_name, created_by = (
            DEFAULT_REGION,
            region,
            albion_guild_id,
            albion_guild_name,
        )
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO guild_binding
                (kook_guild_id, region, albion_guild_id, albion_guild_name, created_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(kook_guild_id, region) DO UPDATE SET
                albion_guild_id=excluded.albion_guild_id,
                albion_guild_name=excluded.albion_guild_name,
                created_by=excluded.created_by
            """,
            (kook_guild_id, region, albion_guild_id, albion_guild_name, created_by),
        )
        conn.commit()
    finally:
        conn.close()


def get_guild_binding(kook_guild_id: str, region: str = DEFAULT_REGION) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM guild_binding WHERE kook_guild_id=? AND region=?",
            (kook_guild_id, region),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def all_guild_bindings(region: str | None = None) -> list[dict]:
    """所有已绑定公会的服务器（定时任务遍历用）。"""
    conn = get_conn()
    try:
        if region is None:
            rows = conn.execute("SELECT * FROM guild_binding").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM guild_binding WHERE region=?", (region,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_player_bindings(kook_guild_id: str, region: str = DEFAULT_REGION) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM player_binding WHERE kook_guild_id=? AND region=?",
            (kook_guild_id, region),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def unbind_guild(kook_guild_id: str, region: str = DEFAULT_REGION) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM guild_binding WHERE kook_guild_id=? AND region=?",
            (kook_guild_id, region),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_setting(
    kook_guild_id: str,
    region: str,
    field: str | None = None,
    value: Any = _MISSING,
) -> bool:
    """更新单个设置字段；公会未绑定返回 False。"""
    if value is _MISSING:
        region, field, value = DEFAULT_REGION, region, field
    elif not _is_region(region):
        region, field, value = DEFAULT_REGION, region, field
    if field not in SETTING_FIELDS:
        raise ValueError(f"非法设置字段: {field}")
    conn = get_conn()
    try:
        cur = conn.execute(
            f"UPDATE guild_binding SET {field}=? WHERE kook_guild_id=? AND region=?",
            (value, kook_guild_id, region),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# --- 自动战报去重 ---

def has_seen_battle_report(
    kook_guild_id: str, region: str, battle_id: str | None = None
) -> bool:
    if battle_id is None:
        region, battle_id = DEFAULT_REGION, region
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT 1 FROM battle_report_seen
            WHERE kook_guild_id=? AND region=? AND battle_id=?
            """,
            (kook_guild_id, region, str(battle_id)),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def mark_battle_report_seen(
    kook_guild_id: str, region: str, battle_id: str | None = None
) -> None:
    if battle_id is None:
        region, battle_id = DEFAULT_REGION, region
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO battle_report_seen (kook_guild_id, region, battle_id)
            VALUES (?, ?, ?)
            """,
            (kook_guild_id, region, str(battle_id)),
        )
        conn.commit()
    finally:
        conn.close()


# --- 击杀/阵亡播报去重 ---

def has_seen_event_broadcast(
    kook_guild_id: str, region: str, event_id: str | None = None
) -> bool:
    if event_id is None:
        region, event_id = DEFAULT_REGION, region
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT 1 FROM event_broadcast_seen
            WHERE kook_guild_id=? AND region=? AND event_id=?
            """,
            (kook_guild_id, region, str(event_id)),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def mark_event_broadcast_seen(
    kook_guild_id: str, region: str, event_id: str | None = None
) -> None:
    if event_id is None:
        region, event_id = DEFAULT_REGION, region
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO event_broadcast_seen
                (kook_guild_id, region, event_id)
            VALUES (?, ?, ?)
            """,
            (kook_guild_id, region, str(event_id)),
        )
        conn.commit()
    finally:
        conn.close()


# --- 出勤/前端只读缓存 ---

def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _field(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row:
            return row.get(key)
    return default


def _as_list(value: Any) -> list:
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return value
    return []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _battle_id(row: dict[str, Any]) -> str:
    return str(
        _field(row, "id", "Id", "albionId", "battleId", "BattleId", default="")
        or ""
    )


def _player_id(row: dict[str, Any]) -> str:
    return str(_field(row, "id", "Id", "playerId", "PlayerId", default="") or "")


def _event_id(row: dict[str, Any]) -> str:
    return str(_field(row, "EventId", "eventId", "id", "Id", default="") or "")


def _event_time(row: dict[str, Any]) -> str:
    return str(_field(row, "TimeStamp", "timestamp", "event_time", "time", default="") or "")


def _event_fame(row: dict[str, Any]) -> int:
    return _int(_field(row, "TotalVictimKillFame", "totalVictimKillFame", "fame", default=0))


def _nested_guild_id(row: dict[str, Any], side: str) -> str:
    nested = row.get(side) or row.get(side.lower()) or {}
    if not isinstance(nested, dict):
        return ""
    return str(_field(nested, "GuildId", "guildId", default="") or "")


def save_guild_member_snapshot(
    kook_guild_id: str,
    region: str,
    albion_guild_id: str | list[dict],
    members: list[dict] | None = None,
    *,
    captured_at: str | None = None,
) -> str:
    if members is None:
        region, albion_guild_id, members = DEFAULT_REGION, region, albion_guild_id
    captured_at = captured_at or _utc_now()
    conn = get_conn()
    try:
        conn.executemany(
            """
            INSERT OR IGNORE INTO guild_member_snapshot
                (kook_guild_id, region, albion_guild_id, captured_at, albion_player_id, albion_player_name)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    kook_guild_id,
                    region,
                    albion_guild_id,
                    captured_at,
                    str(_field(member, "Id", "id", "playerId", "PlayerId", default="") or ""),
                    str(_field(member, "Name", "name", default="") or ""),
                )
                for member in members or []
                if _field(member, "Id", "id", "playerId", "PlayerId", default="")
            ],
        )
        conn.commit()
        return captured_at
    finally:
        conn.close()


def upsert_battle_snapshot(region: str | dict, row: dict | None = None) -> None:
    if row is None:
        region, row = DEFAULT_REGION, region
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO battle_snapshot
                (battle_id, kook_guild_id, region, albion_guild_id, start_time, guild_players,
                 total_players, total_kills, total_fame, captured_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(kook_guild_id, region, battle_id) DO UPDATE SET
                kook_guild_id=excluded.kook_guild_id,
                region=excluded.region,
                albion_guild_id=excluded.albion_guild_id,
                start_time=excluded.start_time,
                guild_players=excluded.guild_players,
                total_players=excluded.total_players,
                total_kills=excluded.total_kills,
                total_fame=excluded.total_fame,
                captured_at=excluded.captured_at
            """,
            (
                str(row["battle_id"]),
                str(row["kook_guild_id"]),
                str(region),
                str(row["albion_guild_id"]),
                str(row.get("start_time") or ""),
                _int(row.get("guild_players")),
                _int(row.get("total_players")),
                _int(row.get("total_kills")),
                _int(row.get("total_fame")),
                str(row.get("captured_at") or _utc_now()),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_battle_participants(
    battle_id: str, region: str | list[dict], rows: list[dict] | None = None
) -> None:
    if rows is None:
        region, rows = DEFAULT_REGION, region
    conn = get_conn()
    try:
        conn.executemany(
            """
            INSERT INTO battle_participant
                (battle_id, region, albion_player_id, albion_player_name, albion_guild_id,
                 kills, deaths, kill_fame)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(battle_id, albion_player_id) DO UPDATE SET
                region=excluded.region,
                albion_player_name=excluded.albion_player_name,
                albion_guild_id=excluded.albion_guild_id,
                kills=excluded.kills,
                deaths=excluded.deaths,
                kill_fame=excluded.kill_fame
            """,
            [
                (
                    str(battle_id),
                    str(region),
                    str(row["albion_player_id"]),
                    str(row.get("albion_player_name") or ""),
                    str(row["albion_guild_id"]),
                    _int(row.get("kills")),
                    _int(row.get("deaths")),
                    _int(row.get("kill_fame")),
                )
                for row in rows or []
                if row.get("albion_player_id") and row.get("albion_guild_id")
            ],
        )
        conn.commit()
    finally:
        conn.close()


def store_battle_detail(
    kook_guild_id: str,
    region: str,
    albion_guild_id: str | dict,
    detail: dict | None = None,
    *,
    captured_at: str | None = None,
) -> str:
    if detail is None:
        region, albion_guild_id, detail = DEFAULT_REGION, region, albion_guild_id
    battle_id = _battle_id(detail)
    if not battle_id:
        raise ValueError("battle detail missing id")
    players = _as_list(_field(detail, "players", "Players", default=[]))
    guild_players = [
        p
        for p in players
        if str(_field(p, "guildId", "GuildId", default="") or "").casefold()
        == albion_guild_id.casefold()
    ]
    upsert_battle_snapshot(
        region,
        {
            "battle_id": battle_id,
            "kook_guild_id": kook_guild_id,
            "albion_guild_id": albion_guild_id,
            "start_time": _field(detail, "startTime", "StartTime", "startedAt", default=""),
            "guild_players": len(guild_players),
            "total_players": _int(
                _field(detail, "totalPlayers", "TotalPlayers", default=len(players))
            ),
            "total_kills": _int(_field(detail, "totalKills", "TotalKills", default=0)),
            "total_fame": _int(_field(detail, "totalFame", "TotalFame", default=0)),
            "captured_at": captured_at or _utc_now(),
        }
    )
    upsert_battle_participants(
        battle_id,
        region,
        [
            {
                "albion_player_id": _player_id(player),
                "albion_player_name": str(_field(player, "name", "Name", default="") or ""),
                "albion_guild_id": str(_field(player, "guildId", "GuildId", default="") or ""),
                "kills": _int(_field(player, "kills", "Kills", default=0)),
                "deaths": _int(_field(player, "deaths", "Deaths", default=0)),
                "kill_fame": _int(_field(player, "killFame", "KillFame", default=0)),
            }
            for player in players
            if _player_id(player)
        ],
    )
    return battle_id


def mark_collector_run(
    name: str,
    kook_guild_id: str,
    region: str = DEFAULT_REGION,
    *,
    status: str = "ok",
    error: str | None = None,
    last_run_at: str | None = None,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO collector_cursor (name, kook_guild_id, region, last_run_at, status, error)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name, kook_guild_id, region) DO UPDATE SET
                last_run_at=excluded.last_run_at,
                status=excluded.status,
                error=excluded.error
            """,
            (name, kook_guild_id, region, last_run_at or _utc_now(), status, error),
        )
        conn.commit()
    finally:
        conn.close()


def recent_collector_runs(limit: int = 10) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT * FROM collector_cursor
            ORDER BY last_run_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit or 10), 50)),),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def recent_attendance_snapshot(
    kook_guild_id: str,
    region: str = DEFAULT_REGION,
    *,
    limit: int = 20,
    min_guild_players: int = 20,
) -> dict:
    binding = get_guild_binding(kook_guild_id, region)
    if not binding:
        return {
            "guild_id": "",
            "battle_count": 0,
            "counted_battle_count": 0,
            "min_guild_players": min_guild_players,
            "member_snapshot_count": 0,
            "member_snapshot_captured_at": None,
            "battle_detail_count": 0,
            "battle_participant_count": 0,
            "members": [],
            "battles": [],
            "skipped_battles": [],
        }
    limit = max(1, min(int(limit or 20), 50))
    conn = get_conn()
    try:
        captured = conn.execute(
            """
            SELECT captured_at FROM guild_member_snapshot
            WHERE kook_guild_id=? AND region=? AND albion_guild_id=?
            ORDER BY captured_at DESC
            LIMIT 1
            """,
            (kook_guild_id, region, binding["albion_guild_id"]),
        ).fetchone()
        members = []
        member_snapshot_captured_at = None
        if captured:
            member_snapshot_captured_at = captured["captured_at"]
            member_rows = conn.execute(
                """
                SELECT albion_player_id AS Id, albion_player_name AS Name
                FROM guild_member_snapshot
                WHERE kook_guild_id=? AND region=? AND albion_guild_id=? AND captured_at=?
                ORDER BY albion_player_name COLLATE NOCASE
                """,
                (kook_guild_id, region, binding["albion_guild_id"], captured["captured_at"]),
            ).fetchall()
            members = [dict(row) for row in member_rows]

        battle_rows = conn.execute(
            """
            SELECT * FROM battle_snapshot
            WHERE kook_guild_id=? AND region=? AND albion_guild_id=?
            ORDER BY start_time DESC, captured_at DESC
            LIMIT ?
            """,
            (kook_guild_id, region, binding["albion_guild_id"], limit),
        ).fetchall()
        details = []
        battle_detail_count = 0
        battle_participant_count = 0
        for battle in battle_rows:
            participant_rows = conn.execute(
                """
                SELECT
                  albion_player_id AS id,
                  albion_player_name AS name,
                  albion_guild_id AS guildId,
                  kills,
                  deaths,
                  kill_fame AS killFame
                FROM battle_participant
                WHERE battle_id=? AND region=?
                """,
                (battle["battle_id"], region),
            ).fetchall()
            if participant_rows:
                battle_detail_count += 1
                battle_participant_count += len(participant_rows)
            details.append(
                {
                    "id": battle["battle_id"],
                    "startTime": battle["start_time"],
                    "totalPlayers": battle["total_players"],
                    "totalKills": battle["total_kills"],
                    "totalFame": battle["total_fame"],
                    "players": [dict(row) for row in participant_rows],
                }
            )
    finally:
        conn.close()
    snapshot = build_attendance_snapshot(
        guild_id=binding["albion_guild_id"],
        members=members,
        battle_details=details,
        min_guild_players=min_guild_players,
    )
    snapshot["member_snapshot_count"] = len(members)
    snapshot["member_snapshot_captured_at"] = member_snapshot_captured_at
    snapshot["battle_detail_count"] = battle_detail_count
    snapshot["battle_participant_count"] = battle_participant_count
    return snapshot


def list_high_fame_events(
    limit: int = 20,
    *,
    kook_guild_id: str | None = None,
    region: str | None = None,
) -> list[dict]:
    conn = get_conn()
    try:
        capped_limit = max(1, min(int(limit or 20), 100))
        if kook_guild_id and region:
            rows = conn.execute(
                """
                SELECT * FROM high_fame_event
                WHERE kook_guild_id=? AND region=?
                ORDER BY event_time DESC
                LIMIT ?
                """,
                (kook_guild_id, region, capped_limit),
            ).fetchall()
            return [_high_fame_event_row(dict(row)) for row in rows]
        if kook_guild_id:
            rows = conn.execute(
                """
                SELECT * FROM high_fame_event
                WHERE kook_guild_id=?
                ORDER BY event_time DESC
                LIMIT ?
                """,
                (kook_guild_id, capped_limit),
            ).fetchall()
            return [_high_fame_event_row(dict(row)) for row in rows]
        rows = conn.execute(
            """
            SELECT * FROM high_fame_event
            WHERE (? IS NULL OR region=?)
            ORDER BY event_time DESC
            LIMIT ?
            """,
            (region, region, capped_limit),
        ).fetchall()
        return [_high_fame_event_row(dict(row)) for row in rows]
    finally:
        conn.close()


def list_leaderboard_snapshots(limit: int = 20) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT * FROM fame_leaderboard_snapshot
            ORDER BY captured_at DESC, id DESC
            LIMIT ?
            """,
            (max(1, min(int(limit or 20), 100)),),
        ).fetchall()
        return [_leaderboard_row(dict(row)) for row in rows]
    finally:
        conn.close()


def save_high_fame_events(
    kook_guild_id: str,
    region: str,
    albion_guild_id: str | list[dict],
    events: list[dict] | None = None,
    *,
    min_fame: int = 1_000_000,
) -> int:
    if events is None:
        region, albion_guild_id, events = DEFAULT_REGION, region, albion_guild_id
    rows = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        event_id = _event_id(event)
        if not event_id or _event_fame(event) < min_fame:
            continue
        killer_guild = _nested_guild_id(event, "Killer")
        victim_guild = _nested_guild_id(event, "Victim")
        if albion_guild_id not in {killer_guild, victim_guild}:
            continue
        rows.append(
            (
                event_id,
                kook_guild_id,
                region,
                _event_time(event),
                _json_dumps(event),
            )
        )
    conn = get_conn()
    try:
        conn.executemany(
            """
            INSERT INTO high_fame_event
                (event_id, kook_guild_id, region, event_time, payload_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(kook_guild_id, region, event_id) DO UPDATE SET
                kook_guild_id=excluded.kook_guild_id,
                region=excluded.region,
                event_time=excluded.event_time,
                payload_json=excluded.payload_json
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def save_leaderboard_snapshot(
    kind: str,
    payload: Any,
    *,
    kook_guild_id: str | None = None,
    captured_at: str | None = None,
    keep_per_kind: int = 12,
) -> str:
    captured_at = captured_at or _utc_now()
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO fame_leaderboard_snapshot
                (kook_guild_id, kind, captured_at, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (kook_guild_id, kind, captured_at, _json_dumps(payload)),
        )
        _prune_leaderboard_snapshots_conn(conn, keep_per_kind=keep_per_kind)
        conn.commit()
        return captured_at
    finally:
        conn.close()


def save_gold_price_snapshot(
    rows: list[dict],
    *,
    captured_at: str | None = None,
    keep: int = 96,
) -> str:
    captured_at = captured_at or _utc_now()
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO gold_price_snapshot (captured_at, payload_json)
            VALUES (?, ?)
            ON CONFLICT(captured_at) DO UPDATE SET
                payload_json=excluded.payload_json
            """,
            (captured_at, _json_dumps(rows or [])),
        )
        _prune_gold_price_snapshots_conn(conn, keep=keep)
        conn.commit()
        return captured_at
    finally:
        conn.close()


def list_gold_price_snapshots(limit: int = 20) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT * FROM gold_price_snapshot
            ORDER BY captured_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit or 20), 100)),),
        ).fetchall()
        return [_gold_price_row(dict(row)) for row in rows]
    finally:
        conn.close()


def prune_leaderboard_snapshots(keep_per_kind: int = 12) -> None:
    conn = get_conn()
    try:
        _prune_leaderboard_snapshots_conn(conn, keep_per_kind=keep_per_kind)
        conn.commit()
    finally:
        conn.close()


def prune_gold_price_snapshots(keep: int = 96) -> None:
    conn = get_conn()
    try:
        _prune_gold_price_snapshots_conn(conn, keep=keep)
        conn.commit()
    finally:
        conn.close()


def _prune_leaderboard_snapshots_conn(conn, *, keep_per_kind: int) -> None:
    keep = max(1, int(keep_per_kind or 12))
    kinds = [
        row["kind"]
        for row in conn.execute(
            "SELECT DISTINCT kind FROM fame_leaderboard_snapshot"
        ).fetchall()
    ]
    for kind in kinds:
        conn.execute(
            """
            DELETE FROM fame_leaderboard_snapshot
            WHERE kind=?
              AND id NOT IN (
                SELECT id FROM fame_leaderboard_snapshot
                WHERE kind=?
                ORDER BY captured_at DESC, id DESC
                LIMIT ?
              )
            """,
            (kind, kind, keep),
        )


def _prune_gold_price_snapshots_conn(conn, *, keep: int) -> None:
    limit = max(1, int(keep or 96))
    conn.execute(
        """
        DELETE FROM gold_price_snapshot
        WHERE captured_at NOT IN (
          SELECT captured_at FROM gold_price_snapshot
          ORDER BY captured_at DESC
          LIMIT ?
        )
        """,
        (limit,),
    )


def _high_fame_event_row(row: dict[str, Any]) -> dict:
    payload = _json_loads(row.get("payload_json"), {})
    killer = payload.get("Killer") or payload.get("killer") or {}
    victim = payload.get("Victim") or payload.get("victim") or {}
    return {
        "event_id": row.get("event_id"),
        "kook_guild_id": row.get("kook_guild_id"),
        "event_time": row.get("event_time"),
        "fame": _event_fame(payload) if isinstance(payload, dict) else 0,
        "killer": {
            "name": _field(killer, "Name", "name", default="") if isinstance(killer, dict) else "",
            "guild": _field(killer, "GuildName", "guildName", default="")
            if isinstance(killer, dict)
            else "",
            "guild_id": _field(killer, "GuildId", "guildId", default="")
            if isinstance(killer, dict)
            else "",
        },
        "victim": {
            "name": _field(victim, "Name", "name", default="") if isinstance(victim, dict) else "",
            "guild": _field(victim, "GuildName", "guildName", default="")
            if isinstance(victim, dict)
            else "",
            "guild_id": _field(victim, "GuildId", "guildId", default="")
            if isinstance(victim, dict)
            else "",
        },
        "payload": payload,
    }


def _leaderboard_row(row: dict[str, Any]) -> dict:
    return {
        "id": row.get("id"),
        "kook_guild_id": row.get("kook_guild_id"),
        "kind": row.get("kind"),
        "captured_at": row.get("captured_at"),
        "items": _json_loads(row.get("payload_json"), []),
    }


def _gold_price_row(row: dict[str, Any]) -> dict:
    return {
        "captured_at": row.get("captured_at"),
        "items": _json_loads(row.get("payload_json"), []),
    }


# --- 玩家绑定 ---

def get_player_binding(
    kook_user_id: str, kook_guild_id: str, region: str = DEFAULT_REGION
) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT * FROM player_binding
            WHERE kook_user_id=? AND kook_guild_id=? AND region=?
            """,
            (kook_user_id, kook_guild_id, region),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_binding_by_player(
    kook_guild_id: str, region: str, albion_player_id: str | None = None
) -> Optional[dict]:
    """同一角色是否已被本服其他 KOOK 用户绑定（防冒名重复绑）。"""
    if albion_player_id is None:
        region, albion_player_id = DEFAULT_REGION, region
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT * FROM player_binding
            WHERE kook_guild_id=? AND region=? AND albion_player_id=?
            """,
            (kook_guild_id, region, albion_player_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_player_binding(
    kook_user_id: str,
    kook_guild_id: str,
    region: str,
    albion_player_id: str | None = None,
    albion_player_name: str | None = None,
    custom_nickname: str | None = None,
) -> None:
    if not _is_region(region):
        region, albion_player_id, albion_player_name, custom_nickname = (
            DEFAULT_REGION,
            region,
            albion_player_id,
            albion_player_name,
        )
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO player_binding
                (kook_user_id, kook_guild_id, region, albion_player_id,
                 albion_player_name, custom_nickname, status)
            VALUES (?, ?, ?, ?, ?, ?, 'verified')
            ON CONFLICT(kook_user_id, kook_guild_id, region) DO UPDATE SET
                albion_player_id=excluded.albion_player_id,
                albion_player_name=excluded.albion_player_name,
                custom_nickname=excluded.custom_nickname,
                status='verified'
            """,
            (
                kook_user_id,
                kook_guild_id,
                region,
                albion_player_id,
                albion_player_name,
                custom_nickname,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def delete_player_binding(
    kook_user_id: str, kook_guild_id: str, region: str = DEFAULT_REGION
) -> Optional[dict]:
    """删除绑定，返回被删的记录（供撤身份组用）。"""
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT * FROM player_binding
            WHERE kook_user_id=? AND kook_guild_id=? AND region=?
            """,
            (kook_user_id, kook_guild_id, region),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            """
            DELETE FROM player_binding
            WHERE kook_user_id=? AND kook_guild_id=? AND region=?
            """,
            (kook_user_id, kook_guild_id, region),
        )
        conn.commit()
        return dict(row)
    finally:
        conn.close()


# --- 待审批 ---

def get_open_pending(
    kook_user_id: str, kook_guild_id: str, region: str = DEFAULT_REGION
) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT * FROM pending_approval
            WHERE kook_user_id=? AND kook_guild_id=? AND region=? AND status='pending'
            """,
            (kook_user_id, kook_guild_id, region),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_pending(
    kook_guild_id: str,
    region: str,
    kook_user_id: str | None = None,
    albion_player_id: str | None = None,
    albion_player_name: str | None = None,
    custom_nickname: str | None = None,
) -> int:
    if not _is_region(region):
        region, kook_user_id, albion_player_id, albion_player_name, custom_nickname = (
            DEFAULT_REGION,
            region,
            kook_user_id,
            albion_player_id,
            albion_player_name,
        )
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO pending_approval
                (kook_guild_id, region, kook_user_id, albion_player_id,
                 albion_player_name, custom_nickname)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                kook_guild_id,
                region,
                kook_user_id,
                albion_player_id,
                albion_player_name,
                custom_nickname,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def set_pending_message(pending_id: int, message_id: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE pending_approval SET message_id=? WHERE id=?", (message_id, pending_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_pending(pending_id: int) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM pending_approval WHERE id=?", (pending_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_pending_status(pending_id: int, status: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE pending_approval SET status=? WHERE id=?", (status, pending_id)
        )
        conn.commit()
    finally:
        conn.close()


# --- 补装申请 ---

def create_regear(
    kook_guild_id: str,
    region: str,
    kook_user_id: str | None = None,
    albion_player_id: str | None = None,
    event_id: str | None = None,
    est_value: int | None = None,
) -> int:
    if not _is_region(region):
        region, kook_user_id, albion_player_id, event_id, est_value = (
            DEFAULT_REGION,
            region,
            kook_user_id,
            albion_player_id,
            event_id,
        )
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO regear_request
                (kook_guild_id, region, kook_user_id, albion_player_id, event_id, est_value)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (kook_guild_id, region, kook_user_id, albion_player_id, event_id, est_value),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_regear(regear_id: int) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM regear_request WHERE id=?", (regear_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_regear(
    kook_guild_id: str,
    region: str = DEFAULT_REGION,
    statuses: tuple[str, ...] | None = None,
    limit: int = 10,
) -> list[dict]:
    """List regear requests for admin queue views."""
    if isinstance(region, tuple):
        statuses, region = region, DEFAULT_REGION
    limit = max(1, min(int(limit or 10), 50))
    conn = get_conn()
    try:
        params: list = [kook_guild_id, region]
        where = "kook_guild_id=? AND region=?"
        if statuses:
            marks = ",".join("?" for _ in statuses)
            where += f" AND status IN ({marks})"
            params.extend(statuses)
        rows = conn.execute(
            f"""
            SELECT * FROM regear_request
            WHERE {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_user_regear(
    kook_guild_id: str,
    region: str,
    kook_user_id: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """List one member's recent regear requests for /补装状态."""
    if kook_user_id is None:
        region, kook_user_id = DEFAULT_REGION, region
    limit = max(1, min(int(limit or 5), 20))
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT * FROM regear_request
            WHERE kook_guild_id=? AND region=? AND kook_user_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (kook_guild_id, region, kook_user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_regear_message(regear_id: int, message_id: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE regear_request SET message_id=? WHERE id=?", (message_id, regear_id)
        )
        conn.commit()
    finally:
        conn.close()


def update_regear_est_value(regear_id: int, est_value: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE regear_request SET est_value=? WHERE id=?",
            (int(est_value), regear_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_regear_status(regear_id: int, status: str, reviewed_by: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE regear_request SET status=?, reviewed_by=?, reviewed_at=datetime('now') WHERE id=?",
            (status, reviewed_by, regear_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_regear_rejected(regear_id: int, reviewed_by: str, reason: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE regear_request
            SET status='rejected', reviewed_by=?, reviewed_at=datetime('now'), reject_reason=?
            WHERE id=?
            """,
            (reviewed_by, reason, regear_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_regear_paid(
    regear_id: int,
    paid_by: str,
    payout_method: str | None = None,
    payout_note: str | None = None,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE regear_request
            SET status='paid', paid_by=?, paid_at=datetime('now'), payout_method=?, payout_note=?
            WHERE id=?
            """,
            (paid_by, payout_method, payout_note, regear_id),
        )
        conn.commit()
    finally:
        conn.close()


# --- 补装审核身份申请 ---

def create_regear_reviewer_request(
    kook_guild_id: str, region: str, kook_user_id: str | None = None
) -> int:
    if kook_user_id is None:
        region, kook_user_id = DEFAULT_REGION, region
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO regear_reviewer_request (kook_guild_id, region, kook_user_id)
            VALUES (?, ?, ?)
            """,
            (kook_guild_id, region, kook_user_id),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_open_regear_reviewer_request(
    kook_guild_id: str, region: str, kook_user_id: str | None = None
) -> Optional[dict]:
    if kook_user_id is None:
        region, kook_user_id = DEFAULT_REGION, region
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT * FROM regear_reviewer_request
            WHERE kook_guild_id=? AND region=? AND kook_user_id=? AND status='pending'
            """,
            (kook_guild_id, region, kook_user_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_regear_reviewer_request_message(request_id: int, message_id: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE regear_reviewer_request SET message_id=? WHERE id=?",
            (message_id, request_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_regear_reviewer_request(request_id: int) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM regear_reviewer_request WHERE id=?", (request_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_regear_reviewer_request_status(request_id: int, status: str, reviewed_by: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE regear_reviewer_request
            SET status=?, reviewed_by=?, reviewed_at=datetime('now')
            WHERE id=?
            """,
            (status, reviewed_by, request_id),
        )
        conn.commit()
    finally:
        conn.close()


# --- 市场低价参考 ---

def upsert_price_references(records: list[dict]) -> int:
    """批量写入武器/副手低价参考，返回写入记录数。"""
    if not records:
        return 0
    rows = [
        (
            r["item_id"],
            int(r["quality"]),
            r["slot_group"],
            int(r["low_price"]),
            int(r.get("sample_count") or 0),
            r.get("source") or "aodp_prices_sell_min",
        )
        for r in records
        if r.get("item_id") and int(r.get("quality") or 0) > 0 and int(r.get("low_price") or 0) > 0
    ]
    if not rows:
        return 0

    conn = get_conn()
    try:
        conn.executemany(
            """
            INSERT INTO market_price_reference
                (item_id, quality, slot_group, low_price, sample_count, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(item_id, quality) DO UPDATE SET
                slot_group=excluded.slot_group,
                low_price=excluded.low_price,
                sample_count=excluded.sample_count,
                source=excluded.source,
                updated_at=datetime('now')
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def get_price_reference(item_id: str, quality: int) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT * FROM market_price_reference
            WHERE item_id=? AND quality=?
            """,
            (item_id, int(quality or 1)),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def count_price_references() -> int:
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM market_price_reference").fetchone()
        return int(row["c"] if row else 0)
    finally:
        conn.close()
