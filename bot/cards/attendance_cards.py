"""Attendance snapshot cards."""
from __future__ import annotations

from khl.card import Card, CardMessage, Element, Module, Types

from bot.cards.query_cards import beijing, fmt


def attendance_card(
    guild_name: str,
    snapshot: dict,
    *,
    requested_battles: int = 20,
    top_limit: int = 10,
) -> CardMessage:
    members = list(snapshot.get("members") or [])
    counted = int(snapshot.get("counted_battle_count") or 0)
    checked = int(snapshot.get("battle_count") or 0)
    threshold = int(snapshot.get("min_guild_players") or 20)
    top = [m for m in members if int(m.get("participated_battles") or 0) > 0][:top_limit]
    low = sorted(
        members,
        key=lambda m: (
            int(m.get("participated_battles") or 0),
            str(m.get("last_seen_at") or ""),
            str(m.get("name") or "").casefold(),
        ),
    )[:top_limit]

    card = Card(
        Module.Header(f"{guild_name} 战斗参与快照"),
        _section(
            "摘要",
            [
                f"最近 `{requested_battles}` 场候选，已拉取 `{checked}` 场详情，计入 `{counted}` 场。",
                f"计入口径：本会参战人数至少 `{threshold}` 人。",
                "战斗参与快照，不等同正式 CTA 考勤，不作为奖惩自动依据。",
            ],
        ),
        Module.Divider(),
        _section("Top 参与成员", _member_lines(top) or ["暂无计入战斗。"]),
        Module.Divider(),
        _section("低参与 / 未参与", _member_lines(low) or ["暂无成员数据。"]),
    )
    return CardMessage(card)


def _member_lines(rows: list[dict]) -> list[str]:
    lines = []
    for idx, row in enumerate(rows, start=1):
        name = row.get("name") or row.get("albion_player_id") or "未知成员"
        battles = int(row.get("participated_battles") or 0)
        rate = int(row.get("participation_rate") or 0)
        last_seen = beijing(str(row.get("last_seen_at") or "")) or "无"
        kills = int(row.get("kills") or 0)
        deaths = int(row.get("deaths") or 0)
        kill_fame = fmt(row.get("kill_fame") or 0)
        lines.append(
            f"{idx}. `{name}`　参与 `{battles}` 场　参与率 `{rate}%`　"
            f"最近 `{last_seen}`　K/D `{kills}/{deaths}`　击杀声望 `{kill_fame}`"
        )
    return lines


def _section(title: str, lines: list[str]) -> Module.Section:
    return Module.Section(
        Element.Text(f"**{title}**\n" + "\n".join(lines), Types.Text.KMD)
    )
