"""绑定关系读写。低频小数据，每次开短连接即可。"""
from typing import Optional

from bot.store.db import get_conn

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
    "member_change_channel_id",
    "regear_reviewer_role_ids",
    "trusted_role_ids",
    "kill_fame_threshold",
}


def bind_guild(
    kook_guild_id: str,
    albion_guild_id: str,
    albion_guild_name: str,
    created_by: str,
) -> None:
    """绑定/改绑公会（同一 KOOK 服务器只留一条，冲突即覆盖核心字段，保留已有设置）。"""
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO guild_binding (kook_guild_id, albion_guild_id, albion_guild_name, created_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(kook_guild_id) DO UPDATE SET
                albion_guild_id=excluded.albion_guild_id,
                albion_guild_name=excluded.albion_guild_name,
                created_by=excluded.created_by
            """,
            (kook_guild_id, albion_guild_id, albion_guild_name, created_by),
        )
        conn.commit()
    finally:
        conn.close()


def get_guild_binding(kook_guild_id: str) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM guild_binding WHERE kook_guild_id=?", (kook_guild_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def all_guild_bindings() -> list[dict]:
    """所有已绑定公会的服务器（定时任务遍历用）。"""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM guild_binding").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_player_bindings(kook_guild_id: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM player_binding WHERE kook_guild_id=?", (kook_guild_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def unbind_guild(kook_guild_id: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM guild_binding WHERE kook_guild_id=?", (kook_guild_id,)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_setting(kook_guild_id: str, field: str, value) -> bool:
    """更新单个设置字段；公会未绑定返回 False。"""
    if field not in SETTING_FIELDS:
        raise ValueError(f"非法设置字段: {field}")
    conn = get_conn()
    try:
        cur = conn.execute(
            f"UPDATE guild_binding SET {field}=? WHERE kook_guild_id=?",
            (value, kook_guild_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# --- 玩家绑定 ---

def get_player_binding(kook_user_id: str, kook_guild_id: str) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM player_binding WHERE kook_user_id=? AND kook_guild_id=?",
            (kook_user_id, kook_guild_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_binding_by_player(kook_guild_id: str, albion_player_id: str) -> Optional[dict]:
    """同一角色是否已被本服其他 KOOK 用户绑定（防冒名重复绑）。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM player_binding WHERE kook_guild_id=? AND albion_player_id=?",
            (kook_guild_id, albion_player_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_player_binding(
    kook_user_id: str,
    kook_guild_id: str,
    albion_player_id: str,
    albion_player_name: str,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO player_binding
                (kook_user_id, kook_guild_id, albion_player_id, albion_player_name, status)
            VALUES (?, ?, ?, ?, 'verified')
            ON CONFLICT(kook_user_id, kook_guild_id) DO UPDATE SET
                albion_player_id=excluded.albion_player_id,
                albion_player_name=excluded.albion_player_name,
                status='verified'
            """,
            (kook_user_id, kook_guild_id, albion_player_id, albion_player_name),
        )
        conn.commit()
    finally:
        conn.close()


def delete_player_binding(kook_user_id: str, kook_guild_id: str) -> Optional[dict]:
    """删除绑定，返回被删的记录（供撤身份组用）。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM player_binding WHERE kook_user_id=? AND kook_guild_id=?",
            (kook_user_id, kook_guild_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "DELETE FROM player_binding WHERE kook_user_id=? AND kook_guild_id=?",
            (kook_user_id, kook_guild_id),
        )
        conn.commit()
        return dict(row)
    finally:
        conn.close()


# --- 待审批 ---

def get_open_pending(kook_user_id: str, kook_guild_id: str) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM pending_approval WHERE kook_user_id=? AND kook_guild_id=? AND status='pending'",
            (kook_user_id, kook_guild_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_pending(
    kook_guild_id: str,
    kook_user_id: str,
    albion_player_id: str,
    albion_player_name: str,
) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO pending_approval
                (kook_guild_id, kook_user_id, albion_player_id, albion_player_name)
            VALUES (?, ?, ?, ?)
            """,
            (kook_guild_id, kook_user_id, albion_player_id, albion_player_name),
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
    kook_user_id: str,
    albion_player_id: str,
    event_id: str,
    est_value: int,
) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO regear_request
                (kook_guild_id, kook_user_id, albion_player_id, event_id, est_value)
            VALUES (?, ?, ?, ?, ?)
            """,
            (kook_guild_id, kook_user_id, albion_player_id, event_id, est_value),
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
    kook_guild_id: str, statuses: tuple[str, ...] | None = None, limit: int = 10
) -> list[dict]:
    """List regear requests for admin queue views."""
    limit = max(1, min(int(limit or 10), 50))
    conn = get_conn()
    try:
        params: list = [kook_guild_id]
        where = "kook_guild_id=?"
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


def list_user_regear(kook_guild_id: str, kook_user_id: str, limit: int = 5) -> list[dict]:
    """List one member's recent regear requests for /补装状态."""
    limit = max(1, min(int(limit or 5), 20))
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT * FROM regear_request
            WHERE kook_guild_id=? AND kook_user_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (kook_guild_id, kook_user_id, limit),
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

def create_regear_reviewer_request(kook_guild_id: str, kook_user_id: str) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO regear_reviewer_request (kook_guild_id, kook_user_id)
            VALUES (?, ?)
            """,
            (kook_guild_id, kook_user_id),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_open_regear_reviewer_request(kook_guild_id: str, kook_user_id: str) -> Optional[dict]:
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT * FROM regear_reviewer_request
            WHERE kook_guild_id=? AND kook_user_id=? AND status='pending'
            """,
            (kook_guild_id, kook_user_id),
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
