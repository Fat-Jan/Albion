"""SQLite 存储：绑定关系 + 审批 + 补装。数据量小，用 stdlib sqlite3 同步即可。

列在计划第六节基础上补了 M2+ 设置项所需字段（播报频道/击杀播报频道/阵亡播报频道/成员变动频道/可信身份组/大额阈值）。
"""
import os
import sqlite3
from typing import Optional

from bot import config

SCHEMA = """
-- 公会绑定（一个 KOOK 服务器绑一个公会）
CREATE TABLE IF NOT EXISTS guild_binding (
  kook_guild_id        TEXT PRIMARY KEY,
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
  member_change_channel_id TEXT,
  regear_reviewer_role_ids TEXT,             -- 逗号分隔：可审批/发放补装的身份组
  trusted_role_ids     TEXT,                 -- 角色预检：逗号分隔的可信身份组
  kill_fame_threshold  INTEGER DEFAULT 100000,-- 死亡播报大额高亮门槛
  created_by           TEXT,
  created_at           TEXT DEFAULT (datetime('now'))
);

-- 玩家绑定
CREATE TABLE IF NOT EXISTS player_binding (
  kook_user_id       TEXT NOT NULL,
  kook_guild_id      TEXT NOT NULL,
  albion_player_id   TEXT NOT NULL,
  albion_player_name TEXT NOT NULL,
  status             TEXT DEFAULT 'verified',
  bound_at           TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (kook_user_id, kook_guild_id)
);

-- 待审批
CREATE TABLE IF NOT EXISTS pending_approval (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  kook_guild_id      TEXT NOT NULL,
  kook_user_id       TEXT NOT NULL,
  albion_player_id   TEXT NOT NULL,
  albion_player_name TEXT NOT NULL,
  message_id         TEXT,
  status             TEXT DEFAULT 'pending', -- pending/approved/rejected
  created_at         TEXT DEFAULT (datetime('now'))
);

-- 补装申请
CREATE TABLE IF NOT EXISTS regear_request (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  kook_guild_id    TEXT NOT NULL,
  kook_user_id     TEXT NOT NULL,
  albion_player_id TEXT,
  event_id         TEXT,
  est_value        INTEGER,
  message_id       TEXT,
  status           TEXT DEFAULT 'pending',  -- pending/approved/rejected/paid
  created_at       TEXT DEFAULT (datetime('now')),
  reviewed_by      TEXT,
  reviewed_at      TEXT,
  paid_by          TEXT,
  paid_at          TEXT
);

-- 补装审核身份申请
CREATE TABLE IF NOT EXISTS regear_reviewer_request (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  kook_guild_id    TEXT NOT NULL,
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
        _ensure_regear_columns(conn)
        _ensure_guild_binding_columns(conn)
        conn.commit()
    finally:
        conn.close()


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


def _ensure_guild_binding_columns(conn: sqlite3.Connection) -> None:
    """Idempotent lightweight migrations for existing guild settings."""
    cols = {
        row["name"] if isinstance(row, sqlite3.Row) else row[1]
        for row in conn.execute("PRAGMA table_info(guild_binding)")
    }
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
    if "kill_broadcast_channel_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN kill_broadcast_channel_id TEXT")
    if "death_broadcast_channel_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN death_broadcast_channel_id TEXT")
    if "member_change_channel_id" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN member_change_channel_id TEXT")
    if "regear_reviewer_role_ids" not in cols:
        conn.execute("ALTER TABLE guild_binding ADD COLUMN regear_reviewer_role_ids TEXT")


if __name__ == "__main__":
    init_db()
    print(f"已初始化 {config.DB_PATH}")
