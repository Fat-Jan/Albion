"""SQLite 存储：绑定关系 + 审批 + 补装。数据量小，用 stdlib sqlite3 同步即可。

列在计划第六节基础上补了 M2+ 设置项所需字段（播报频道/击杀播报频道/阵亡播报频道/战报推送频道/成员变动频道/可信身份组）。
"""
import os
import sqlite3
from typing import Optional

from bot import config

SCHEMA = """
-- 公会绑定（同一个 KOOK 服务器可按 region 绑定不同 Albion 公会）
CREATE TABLE IF NOT EXISTS guild_binding (
  kook_guild_id        TEXT NOT NULL,
  region               TEXT NOT NULL DEFAULT 'eu',
  albion_guild_id      TEXT NOT NULL,
  albion_guild_name    TEXT NOT NULL,
  member_role_id       TEXT,
  approval_channel_id  TEXT,
  regear_channel_id    TEXT,
  regear_apply_channel_id TEXT,
  regear_review_channel_id TEXT,
  regear_payout_channel_id TEXT,
  regear_notify_channel_id TEXT,
  broadcast_channel_id TEXT,
  kill_broadcast_channel_id TEXT,
  death_broadcast_channel_id TEXT,
  battle_report_channel_id TEXT,
  battle_report_min_guild_players INTEGER DEFAULT 10,
  member_change_channel_id TEXT,
  regear_reviewer_role_ids TEXT,             -- 逗号分隔：可审批/发放补装的身份组
  trusted_role_ids     TEXT,                 -- 角色预检：逗号分隔的可信身份组
  kill_fame_threshold  INTEGER DEFAULT 100000,-- 旧版大额阈值字段，保留兼容；当前大额规则由代码固定
  created_by           TEXT,
  created_at           TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (kook_guild_id, region)
);

-- 玩家绑定
CREATE TABLE IF NOT EXISTS player_binding (
  kook_user_id       TEXT NOT NULL,
  kook_guild_id      TEXT NOT NULL,
  region             TEXT NOT NULL DEFAULT 'eu',
  albion_player_id   TEXT NOT NULL,
  albion_player_name TEXT NOT NULL,
  custom_nickname    TEXT,
  status             TEXT DEFAULT 'verified',
  bound_at           TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (kook_user_id, kook_guild_id, region)
);

-- 待审批
CREATE TABLE IF NOT EXISTS pending_approval (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  kook_guild_id      TEXT NOT NULL,
  region             TEXT NOT NULL DEFAULT 'eu',
  kook_user_id       TEXT NOT NULL,
  albion_player_id   TEXT NOT NULL,
  albion_player_name TEXT NOT NULL,
  custom_nickname    TEXT,
  message_id         TEXT,
  status             TEXT DEFAULT 'pending', -- pending/approved/rejected
  created_at         TEXT DEFAULT (datetime('now'))
);

-- 补装申请
CREATE TABLE IF NOT EXISTS regear_request (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  kook_guild_id    TEXT NOT NULL,
  region           TEXT NOT NULL DEFAULT 'eu',
  kook_user_id     TEXT NOT NULL,
  albion_player_id TEXT,
  event_id         TEXT,
  est_value        INTEGER,
  message_id       TEXT,
  status           TEXT DEFAULT 'pending',  -- pending/approved/rejected/paid
  created_at       TEXT DEFAULT (datetime('now')),
  reviewed_by      TEXT,
  reviewed_at      TEXT,
  reject_reason    TEXT,
  paid_by          TEXT,
  paid_at          TEXT,
  payout_method    TEXT, -- silver/equipment/item
  payout_note      TEXT
);

-- 补装审核身份申请
CREATE TABLE IF NOT EXISTS regear_reviewer_request (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  kook_guild_id    TEXT NOT NULL,
  region           TEXT NOT NULL DEFAULT 'eu',
  kook_user_id     TEXT NOT NULL,
  message_id       TEXT,
  status           TEXT DEFAULT 'pending', -- pending/approved/rejected
  created_at       TEXT DEFAULT (datetime('now')),
  reviewed_by      TEXT,
  reviewed_at      TEXT
);

-- 市场低价参考：T4-T8 主手/双手/副手，含附魔 @1-@4；用于实时市场稀疏时兜底。
CREATE TABLE IF NOT EXISTS market_price_reference (
  item_id      TEXT NOT NULL,
  quality      INTEGER NOT NULL,
  slot_group   TEXT NOT NULL, -- mainhand/offhand
  low_price    INTEGER NOT NULL,
  sample_count INTEGER DEFAULT 0,
  source       TEXT DEFAULT 'aodp_prices_sell_min',
  updated_at   TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (item_id, quality)
);

-- 自动战报推送去重：同一 KOOK 服务器一场战役只推一次。
CREATE TABLE IF NOT EXISTS battle_report_seen (
  kook_guild_id TEXT NOT NULL,
  region        TEXT NOT NULL DEFAULT 'eu',
  battle_id     TEXT NOT NULL,
  reported_at   TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (kook_guild_id, region, battle_id)
);

-- 击杀/阵亡播报去重：同一 KOOK 服务器同一区服同一事件只播一次。
CREATE TABLE IF NOT EXISTS event_broadcast_seen (
  kook_guild_id TEXT NOT NULL,
  region        TEXT NOT NULL DEFAULT 'eu',
  event_id      TEXT NOT NULL,
  broadcasted_at TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (kook_guild_id, region, event_id)
);

-- 出勤/前端只读缓存：成员快照。
CREATE TABLE IF NOT EXISTS guild_member_snapshot (
  kook_guild_id      TEXT NOT NULL,
  region             TEXT NOT NULL DEFAULT 'eu',
  albion_guild_id    TEXT NOT NULL,
  captured_at        TEXT NOT NULL,
  albion_player_id   TEXT NOT NULL,
  albion_player_name TEXT NOT NULL,
  PRIMARY KEY (kook_guild_id, region, albion_guild_id, captured_at, albion_player_id)
);

-- 出勤/前端只读缓存：战斗摘要。
CREATE TABLE IF NOT EXISTS battle_snapshot (
  battle_id        TEXT NOT NULL,
  kook_guild_id    TEXT NOT NULL,
  region           TEXT NOT NULL DEFAULT 'eu',
  albion_guild_id  TEXT NOT NULL,
  start_time       TEXT,
  guild_players    INTEGER DEFAULT 0,
  total_players    INTEGER DEFAULT 0,
  total_kills      INTEGER DEFAULT 0,
  total_fame       INTEGER DEFAULT 0,
  captured_at      TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (kook_guild_id, region, battle_id)
);

-- 出勤/前端只读缓存：单场本会参与者。
CREATE TABLE IF NOT EXISTS battle_participant (
  battle_id          TEXT NOT NULL,
  region             TEXT NOT NULL DEFAULT 'eu',
  albion_player_id   TEXT NOT NULL,
  albion_player_name TEXT NOT NULL,
  albion_guild_id    TEXT NOT NULL,
  kills              INTEGER DEFAULT 0,
  deaths             INTEGER DEFAULT 0,
  kill_fame          INTEGER DEFAULT 0,
  PRIMARY KEY (battle_id, albion_player_id)
);

-- 采集器游标和状态。
CREATE TABLE IF NOT EXISTS collector_cursor (
  name          TEXT NOT NULL,
  kook_guild_id TEXT NOT NULL,
  region        TEXT NOT NULL DEFAULT 'eu',
  last_run_at   TEXT,
  status        TEXT DEFAULT 'ok',
  error         TEXT,
  PRIMARY KEY (name, kook_guild_id, region)
);

-- P1 API 预留：没有采集数据时 API 返回空数组而不是 500。
CREATE TABLE IF NOT EXISTS high_fame_event (
  event_id      TEXT NOT NULL,
  kook_guild_id TEXT NOT NULL,
  region        TEXT NOT NULL DEFAULT 'eu',
  event_time    TEXT,
  payload_json  TEXT,
  PRIMARY KEY (kook_guild_id, region, event_id)
);

CREATE TABLE IF NOT EXISTS fame_leaderboard_snapshot (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  kook_guild_id TEXT,
  kind          TEXT NOT NULL,
  captured_at   TEXT NOT NULL,
  payload_json  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gold_price_snapshot (
  captured_at   TEXT PRIMARY KEY,
  payload_json  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_battle_participant_battle
ON battle_participant (battle_id);

CREATE INDEX IF NOT EXISTS idx_collector_cursor_last_run
ON collector_cursor (last_run_at DESC);

CREATE INDEX IF NOT EXISTS idx_high_fame_event_time
ON high_fame_event (event_time DESC);

CREATE INDEX IF NOT EXISTS idx_leaderboard_snapshot_kind_time
ON fame_leaderboard_snapshot (kind, captured_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_gold_price_snapshot_time
ON gold_price_snapshot (captured_at DESC);
"""


def get_conn(path: Optional[str] = None) -> sqlite3.Connection:
    path = path or config.DB_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Optional[str] = None) -> None:
    conn = get_conn(path)
    try:
        conn.executescript(SCHEMA)
        _ensure_binding_columns(conn)
        _ensure_regear_columns(conn)
        _ensure_guild_binding_columns(conn)
        _ensure_region_columns(conn)
        _ensure_battle_snapshot_scope(conn)
        _ensure_high_fame_event_scope(conn)
        conn.commit()
    finally:
        conn.close()


def _ensure_binding_columns(conn: sqlite3.Connection) -> None:
    """Idempotent lightweight migrations for player binding and approvals."""
    player_cols = {
        row["name"] if isinstance(row, sqlite3.Row) else row[1]
        for row in conn.execute("PRAGMA table_info(player_binding)")
    }
    if "custom_nickname" not in player_cols:
        conn.execute("ALTER TABLE player_binding ADD COLUMN custom_nickname TEXT")

    pending_cols = {
        row["name"] if isinstance(row, sqlite3.Row) else row[1]
        for row in conn.execute("PRAGMA table_info(pending_approval)")
    }
    if "custom_nickname" not in pending_cols:
        conn.execute("ALTER TABLE pending_approval ADD COLUMN custom_nickname TEXT")


def _ensure_regear_columns(conn: sqlite3.Connection) -> None:
    """Idempotent lightweight migrations for existing SQLite files."""
    cols = {
        row["name"] if isinstance(row, sqlite3.Row) else row[1]
        for row in conn.execute("PRAGMA table_info(regear_request)")
    }
    if "paid_by" not in cols:
        conn.execute("ALTER TABLE regear_request ADD COLUMN paid_by TEXT")
    if "paid_at" not in cols:
        conn.execute("ALTER TABLE regear_request ADD COLUMN paid_at TEXT")
    if "reject_reason" not in cols:
        conn.execute("ALTER TABLE regear_request ADD COLUMN reject_reason TEXT")
    if "payout_method" not in cols:
        conn.execute("ALTER TABLE regear_request ADD COLUMN payout_method TEXT")
    if "payout_note" not in cols:
        conn.execute("ALTER TABLE regear_request ADD COLUMN payout_note TEXT")


def _ensure_guild_binding_columns(conn: sqlite3.Connection) -> None:
    """Idempotent lightweight migrations for existing guild settings."""
    cols = {
        row["name"] if isinstance(row, sqlite3.Row) else row[1]
        for row in conn.execute("PRAGMA table_info(guild_binding)")
    }
    if "member_role_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN member_role_id TEXT")
    if "approval_channel_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN approval_channel_id TEXT")
    if "regear_channel_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN regear_channel_id TEXT")
    if "regear_apply_channel_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN regear_apply_channel_id TEXT")
    if "regear_review_channel_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN regear_review_channel_id TEXT")
    if "regear_payout_channel_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN regear_payout_channel_id TEXT")
    if "regear_notify_channel_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN regear_notify_channel_id TEXT")
    if "broadcast_channel_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN broadcast_channel_id TEXT")
    if "kill_broadcast_channel_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN kill_broadcast_channel_id TEXT")
    if "death_broadcast_channel_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN death_broadcast_channel_id TEXT")
    if "battle_report_channel_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN battle_report_channel_id TEXT")
    if "battle_report_min_guild_players" not in cols:
        conn.execute(
            "ALTER TABLE guild_binding ADD COLUMN battle_report_min_guild_players INTEGER DEFAULT 10"
        )
    if "member_change_channel_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN member_change_channel_id TEXT")
    if "regear_reviewer_role_ids" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN regear_reviewer_role_ids TEXT")
    if "trusted_role_ids" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN trusted_role_ids TEXT")
    if "kill_fame_threshold" not in cols:
        conn.execute(
            "ALTER TABLE guild_binding ADD COLUMN kill_fame_threshold INTEGER DEFAULT 100000"
        )


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, sqlite3.Row]:
    return {
        row["name"] if isinstance(row, sqlite3.Row) else row[1]: row
        for row in conn.execute(f"PRAGMA table_info({table})")
    }


def _legacy_region() -> str:
    region = getattr(config, "KOOK_REGION_CODE_LEGACY", "") or getattr(
        config, "KOOK_REGION_CODE", ""
    )
    region = str(region or "").strip().lower()
    return region if region in {"eu", "asia"} else "eu"


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"])


def _assert_same_count(before: int, after: int, table: str) -> None:
    if before != after:
        raise RuntimeError(f"{table} region migration row count changed: {before} -> {after}")


def _pk_columns(cols: dict[str, sqlite3.Row]) -> tuple[str, ...]:
    return tuple(
        name
        for name, row in sorted(cols.items(), key=lambda item: int(item[1]["pk"] or 0))
        if int(row["pk"] or 0) > 0
    )


def _ensure_region_columns(conn: sqlite3.Connection) -> None:
    """Migrate old single-region SQLite files to explicit region-scoped tables."""
    legacy_region = _legacy_region()
    _ensure_guild_binding_region(conn, legacy_region)
    _ensure_player_binding_region(conn, legacy_region)
    _ensure_simple_region_column(conn, "pending_approval", legacy_region)
    _ensure_simple_region_column(conn, "regear_request", legacy_region)
    _ensure_simple_region_column(conn, "regear_reviewer_request", legacy_region)
    _ensure_battle_report_seen_region(conn, legacy_region)
    _ensure_event_broadcast_seen_region(conn, legacy_region)
    _ensure_guild_member_snapshot_region(conn, legacy_region)
    _ensure_battle_snapshot_region(conn, legacy_region)
    _ensure_battle_participant_region(conn, legacy_region)
    _ensure_collector_cursor_region(conn, legacy_region)
    _ensure_high_fame_event_region(conn, legacy_region)
    _ensure_region_indexes(conn)


def _ensure_simple_region_column(
    conn: sqlite3.Connection, table: str, legacy_region: str
) -> None:
    cols = _columns(conn, table)
    if not cols or "region" in cols:
        return
    before = _table_count(conn, table)
    conn.execute(f"ALTER TABLE {table} ADD COLUMN region TEXT NOT NULL DEFAULT 'eu'")
    conn.execute(f"UPDATE {table} SET region=?", (legacy_region,))
    _assert_same_count(before, _table_count(conn, table), table)


def _ensure_guild_binding_region(conn: sqlite3.Connection, legacy_region: str) -> None:
    cols = _columns(conn, "guild_binding")
    if not cols:
        return
    if _pk_columns(cols) == ("kook_guild_id", "region"):
        return
    _ensure_guild_binding_columns(conn)
    cols = _columns(conn, "guild_binding")
    before = _table_count(conn, "guild_binding")
    region_expr = "COALESCE(region, ?)" if "region" in cols else "?"
    conn.execute("ALTER TABLE guild_binding RENAME TO guild_binding_legacy")
    conn.execute(
        """
        CREATE TABLE guild_binding (
          kook_guild_id        TEXT NOT NULL,
          region               TEXT NOT NULL DEFAULT 'eu',
          albion_guild_id      TEXT NOT NULL,
          albion_guild_name    TEXT NOT NULL,
          member_role_id       TEXT,
          approval_channel_id  TEXT,
          regear_channel_id    TEXT,
          regear_apply_channel_id TEXT,
          regear_review_channel_id TEXT,
          regear_payout_channel_id TEXT,
          regear_notify_channel_id TEXT,
          broadcast_channel_id TEXT,
          kill_broadcast_channel_id TEXT,
          death_broadcast_channel_id TEXT,
          battle_report_channel_id TEXT,
          battle_report_min_guild_players INTEGER DEFAULT 10,
          member_change_channel_id TEXT,
          regear_reviewer_role_ids TEXT,
          trusted_role_ids     TEXT,
          kill_fame_threshold  INTEGER DEFAULT 100000,
          created_by           TEXT,
          created_at           TEXT DEFAULT (datetime('now')),
          PRIMARY KEY (kook_guild_id, region)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO guild_binding (
          kook_guild_id, region, albion_guild_id, albion_guild_name,
          member_role_id, approval_channel_id, regear_channel_id,
          regear_apply_channel_id, regear_review_channel_id,
          regear_payout_channel_id, regear_notify_channel_id,
          broadcast_channel_id, kill_broadcast_channel_id, death_broadcast_channel_id,
          battle_report_channel_id, battle_report_min_guild_players,
          member_change_channel_id, regear_reviewer_role_ids, trusted_role_ids,
          kill_fame_threshold, created_by, created_at
        )
        SELECT
          kook_guild_id, {region_expr}, albion_guild_id, albion_guild_name,
          member_role_id, approval_channel_id, regear_channel_id,
          regear_apply_channel_id, regear_review_channel_id,
          regear_payout_channel_id, regear_notify_channel_id,
          broadcast_channel_id, kill_broadcast_channel_id, death_broadcast_channel_id,
          battle_report_channel_id, COALESCE(battle_report_min_guild_players, 10),
          member_change_channel_id, regear_reviewer_role_ids, trusted_role_ids,
          COALESCE(kill_fame_threshold, 100000), created_by, created_at
        FROM guild_binding_legacy
        """.format(region_expr=region_expr),
        (legacy_region,),
    )
    conn.execute("DROP TABLE guild_binding_legacy")
    _assert_same_count(before, _table_count(conn, "guild_binding"), "guild_binding")


def _ensure_player_binding_region(conn: sqlite3.Connection, legacy_region: str) -> None:
    cols = _columns(conn, "player_binding")
    if not cols:
        return
    if _pk_columns(cols) == ("kook_user_id", "kook_guild_id", "region"):
        return
    _ensure_binding_columns(conn)
    cols = _columns(conn, "player_binding")
    before = _table_count(conn, "player_binding")
    region_expr = "COALESCE(region, ?)" if "region" in cols else "?"
    conn.execute("ALTER TABLE player_binding RENAME TO player_binding_legacy")
    conn.execute(
        """
        CREATE TABLE player_binding (
          kook_user_id       TEXT NOT NULL,
          kook_guild_id      TEXT NOT NULL,
          region             TEXT NOT NULL DEFAULT 'eu',
          albion_player_id   TEXT NOT NULL,
          albion_player_name TEXT NOT NULL,
          custom_nickname    TEXT,
          status             TEXT DEFAULT 'verified',
          bound_at           TEXT DEFAULT (datetime('now')),
          PRIMARY KEY (kook_user_id, kook_guild_id, region)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO player_binding (
          kook_user_id, kook_guild_id, region, albion_player_id,
          albion_player_name, custom_nickname, status, bound_at
        )
        SELECT
          kook_user_id, kook_guild_id, {region_expr}, albion_player_id,
          albion_player_name, custom_nickname, status, bound_at
        FROM player_binding_legacy
        """.format(region_expr=region_expr),
        (legacy_region,),
    )
    conn.execute("DROP TABLE player_binding_legacy")
    _assert_same_count(before, _table_count(conn, "player_binding"), "player_binding")


def _ensure_battle_report_seen_region(conn: sqlite3.Connection, legacy_region: str) -> None:
    cols = _columns(conn, "battle_report_seen")
    if not cols:
        return
    if _pk_columns(cols) == ("kook_guild_id", "region", "battle_id"):
        return
    before = _table_count(conn, "battle_report_seen")
    region_expr = "COALESCE(region, ?)" if "region" in cols else "?"
    conn.execute("ALTER TABLE battle_report_seen RENAME TO battle_report_seen_legacy")
    conn.execute(
        """
        CREATE TABLE battle_report_seen (
          kook_guild_id TEXT NOT NULL,
          region        TEXT NOT NULL DEFAULT 'eu',
          battle_id     TEXT NOT NULL,
          reported_at   TEXT DEFAULT (datetime('now')),
          PRIMARY KEY (kook_guild_id, region, battle_id)
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO battle_report_seen
            (kook_guild_id, region, battle_id, reported_at)
        SELECT kook_guild_id, {region_expr}, battle_id, reported_at
        FROM battle_report_seen_legacy
        """.format(region_expr=region_expr),
        (legacy_region,),
    )
    conn.execute("DROP TABLE battle_report_seen_legacy")
    _assert_same_count(before, _table_count(conn, "battle_report_seen"), "battle_report_seen")


def _ensure_event_broadcast_seen_region(conn: sqlite3.Connection, legacy_region: str) -> None:
    cols = _columns(conn, "event_broadcast_seen")
    if not cols:
        return
    if _pk_columns(cols) == ("kook_guild_id", "region", "event_id"):
        return
    before = _table_count(conn, "event_broadcast_seen")
    region_expr = "COALESCE(region, ?)" if "region" in cols else "?"
    conn.execute("ALTER TABLE event_broadcast_seen RENAME TO event_broadcast_seen_legacy")
    conn.execute(
        """
        CREATE TABLE event_broadcast_seen (
          kook_guild_id TEXT NOT NULL,
          region        TEXT NOT NULL DEFAULT 'eu',
          event_id      TEXT NOT NULL,
          broadcasted_at TEXT DEFAULT (datetime('now')),
          PRIMARY KEY (kook_guild_id, region, event_id)
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO event_broadcast_seen
            (kook_guild_id, region, event_id, broadcasted_at)
        SELECT kook_guild_id, {region_expr}, event_id, broadcasted_at
        FROM event_broadcast_seen_legacy
        """.format(region_expr=region_expr),
        (legacy_region,),
    )
    conn.execute("DROP TABLE event_broadcast_seen_legacy")
    _assert_same_count(
        before,
        _table_count(conn, "event_broadcast_seen"),
        "event_broadcast_seen",
    )


def _ensure_guild_member_snapshot_region(
    conn: sqlite3.Connection, legacy_region: str
) -> None:
    cols = _columns(conn, "guild_member_snapshot")
    if not cols:
        return
    if _pk_columns(cols) == (
        "kook_guild_id",
        "region",
        "albion_guild_id",
        "captured_at",
        "albion_player_id",
    ):
        return
    before = _table_count(conn, "guild_member_snapshot")
    region_expr = "COALESCE(region, ?)" if "region" in cols else "?"
    conn.execute("ALTER TABLE guild_member_snapshot RENAME TO guild_member_snapshot_legacy")
    conn.execute(
        """
        CREATE TABLE guild_member_snapshot (
          kook_guild_id      TEXT NOT NULL,
          region             TEXT NOT NULL DEFAULT 'eu',
          albion_guild_id    TEXT NOT NULL,
          captured_at        TEXT NOT NULL,
          albion_player_id   TEXT NOT NULL,
          albion_player_name TEXT NOT NULL,
          PRIMARY KEY (kook_guild_id, region, albion_guild_id, captured_at, albion_player_id)
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO guild_member_snapshot
            (kook_guild_id, region, albion_guild_id, captured_at,
             albion_player_id, albion_player_name)
        SELECT kook_guild_id, {region_expr}, albion_guild_id, captured_at,
               albion_player_id, albion_player_name
        FROM guild_member_snapshot_legacy
        """.format(region_expr=region_expr),
        (legacy_region,),
    )
    conn.execute("DROP TABLE guild_member_snapshot_legacy")
    _assert_same_count(
        before, _table_count(conn, "guild_member_snapshot"), "guild_member_snapshot"
    )


def _ensure_battle_snapshot_region(conn: sqlite3.Connection, legacy_region: str) -> None:
    cols = _columns(conn, "battle_snapshot")
    if not cols:
        return
    if _pk_columns(cols) == ("kook_guild_id", "region", "battle_id"):
        return
    before = _table_count(conn, "battle_snapshot")
    region_expr = "COALESCE(region, ?)" if "region" in cols else "?"
    conn.execute("ALTER TABLE battle_snapshot RENAME TO battle_snapshot_legacy")
    conn.execute(
        """
        CREATE TABLE battle_snapshot (
          battle_id        TEXT NOT NULL,
          kook_guild_id    TEXT NOT NULL,
          region           TEXT NOT NULL DEFAULT 'eu',
          albion_guild_id  TEXT NOT NULL,
          start_time       TEXT,
          guild_players    INTEGER DEFAULT 0,
          total_players    INTEGER DEFAULT 0,
          total_kills      INTEGER DEFAULT 0,
          total_fame       INTEGER DEFAULT 0,
          captured_at      TEXT DEFAULT (datetime('now')),
          PRIMARY KEY (kook_guild_id, region, battle_id)
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO battle_snapshot
            (battle_id, kook_guild_id, region, albion_guild_id, start_time,
             guild_players, total_players, total_kills, total_fame, captured_at)
        SELECT battle_id, kook_guild_id, {region_expr}, albion_guild_id, start_time,
               guild_players, total_players, total_kills, total_fame, captured_at
        FROM battle_snapshot_legacy
        """.format(region_expr=region_expr),
        (legacy_region,),
    )
    conn.execute("DROP TABLE battle_snapshot_legacy")
    _assert_same_count(before, _table_count(conn, "battle_snapshot"), "battle_snapshot")


def _ensure_battle_participant_region(
    conn: sqlite3.Connection, legacy_region: str
) -> None:
    _ensure_simple_region_column(conn, "battle_participant", legacy_region)


def _ensure_collector_cursor_region(conn: sqlite3.Connection, legacy_region: str) -> None:
    cols = _columns(conn, "collector_cursor")
    if not cols:
        return
    if _pk_columns(cols) == ("name", "kook_guild_id", "region"):
        return
    before = _table_count(conn, "collector_cursor")
    region_expr = "COALESCE(region, ?)" if "region" in cols else "?"
    conn.execute("ALTER TABLE collector_cursor RENAME TO collector_cursor_legacy")
    conn.execute(
        """
        CREATE TABLE collector_cursor (
          name          TEXT NOT NULL,
          kook_guild_id TEXT NOT NULL,
          region        TEXT NOT NULL DEFAULT 'eu',
          last_run_at   TEXT,
          status        TEXT DEFAULT 'ok',
          error         TEXT,
          PRIMARY KEY (name, kook_guild_id, region)
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO collector_cursor
            (name, kook_guild_id, region, last_run_at, status, error)
        SELECT name, kook_guild_id, {region_expr}, last_run_at, status, error
        FROM collector_cursor_legacy
        """.format(region_expr=region_expr),
        (legacy_region,),
    )
    conn.execute("DROP TABLE collector_cursor_legacy")
    _assert_same_count(before, _table_count(conn, "collector_cursor"), "collector_cursor")


def _ensure_high_fame_event_region(conn: sqlite3.Connection, legacy_region: str) -> None:
    cols = _columns(conn, "high_fame_event")
    if not cols:
        return
    if _pk_columns(cols) == ("kook_guild_id", "region", "event_id"):
        return
    before = _table_count(conn, "high_fame_event")
    region_expr = "COALESCE(region, ?)" if "region" in cols else "?"
    conn.execute("ALTER TABLE high_fame_event RENAME TO high_fame_event_legacy")
    conn.execute(
        """
        CREATE TABLE high_fame_event (
          event_id      TEXT NOT NULL,
          kook_guild_id TEXT NOT NULL,
          region        TEXT NOT NULL DEFAULT 'eu',
          event_time    TEXT,
          payload_json  TEXT,
          PRIMARY KEY (kook_guild_id, region, event_id)
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO high_fame_event
            (event_id, kook_guild_id, region, event_time, payload_json)
        SELECT event_id, COALESCE(kook_guild_id, 'global'), {region_expr},
               event_time, payload_json
        FROM high_fame_event_legacy
        """.format(region_expr=region_expr),
        (legacy_region,),
    )
    conn.execute("DROP TABLE high_fame_event_legacy")
    _assert_same_count(before, _table_count(conn, "high_fame_event"), "high_fame_event")


def _ensure_region_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_guild_binding_region
        ON guild_binding(region);

        CREATE INDEX IF NOT EXISTS idx_player_binding_region
        ON player_binding(kook_guild_id, region);

        CREATE INDEX IF NOT EXISTS idx_guild_member_snapshot_latest
        ON guild_member_snapshot (kook_guild_id, region, albion_guild_id, captured_at DESC);

        CREATE INDEX IF NOT EXISTS idx_battle_snapshot_guild_time
        ON battle_snapshot (kook_guild_id, region, albion_guild_id, start_time DESC, captured_at DESC);

        CREATE INDEX IF NOT EXISTS idx_battle_snapshot_region_time
        ON battle_snapshot(kook_guild_id, region, albion_guild_id, start_time DESC);

        CREATE INDEX IF NOT EXISTS idx_high_fame_event_guild_time
        ON high_fame_event (kook_guild_id, region, event_time DESC);

        CREATE INDEX IF NOT EXISTS idx_high_fame_event_time
        ON high_fame_event (event_time DESC);

        CREATE INDEX IF NOT EXISTS idx_high_fame_event_region_time
        ON high_fame_event(kook_guild_id, region, event_time DESC);
        """
    )


def _ensure_battle_snapshot_scope(conn: sqlite3.Connection) -> None:
    """Migrate legacy battle cache from global battle_id PK to per-KOOK-guild scope."""
    cols = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(battle_snapshot)")
    }
    if not cols:
        return
    kook_pk = cols.get("kook_guild_id")
    if kook_pk and int(kook_pk["pk"] or 0) > 0:
        return

    conn.execute("ALTER TABLE battle_snapshot RENAME TO battle_snapshot_legacy")
    conn.execute(
        """
        CREATE TABLE battle_snapshot (
          battle_id        TEXT NOT NULL,
          kook_guild_id    TEXT NOT NULL,
          albion_guild_id  TEXT NOT NULL,
          start_time       TEXT,
          guild_players    INTEGER DEFAULT 0,
          total_players    INTEGER DEFAULT 0,
          total_kills      INTEGER DEFAULT 0,
          total_fame       INTEGER DEFAULT 0,
          captured_at      TEXT DEFAULT (datetime('now')),
          PRIMARY KEY (kook_guild_id, battle_id)
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO battle_snapshot
            (battle_id, kook_guild_id, albion_guild_id, start_time, guild_players,
             total_players, total_kills, total_fame, captured_at)
        SELECT battle_id, kook_guild_id, albion_guild_id, start_time, guild_players,
               total_players, total_kills, total_fame, captured_at
        FROM battle_snapshot_legacy
        """
    )
    conn.execute("DROP TABLE battle_snapshot_legacy")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_battle_snapshot_guild_time
        ON battle_snapshot (kook_guild_id, albion_guild_id, start_time DESC, captured_at DESC)
        """
    )


def _ensure_high_fame_event_scope(conn: sqlite3.Connection) -> None:
    """Migrate high-fame cache from global event_id PK to per-KOOK-guild scope."""
    cols = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(high_fame_event)")
    }
    if not cols:
        return
    kook_pk = cols.get("kook_guild_id")
    if kook_pk and int(kook_pk["pk"] or 0) > 0:
        return

    conn.execute("ALTER TABLE high_fame_event RENAME TO high_fame_event_legacy")
    conn.execute(
        """
        CREATE TABLE high_fame_event (
          event_id      TEXT NOT NULL,
          kook_guild_id TEXT NOT NULL,
          event_time    TEXT,
          payload_json  TEXT,
          PRIMARY KEY (kook_guild_id, event_id)
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO high_fame_event
            (event_id, kook_guild_id, event_time, payload_json)
        SELECT event_id, COALESCE(kook_guild_id, 'global'), event_time, payload_json
        FROM high_fame_event_legacy
        """
    )
    conn.execute("DROP TABLE high_fame_event_legacy")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_high_fame_event_time
        ON high_fame_event (event_time DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_high_fame_event_guild_time
        ON high_fame_event (kook_guild_id, event_time DESC)
        """
    )


if __name__ == "__main__":
    init_db()
    print(f"已初始化 {config.DB_PATH}")
