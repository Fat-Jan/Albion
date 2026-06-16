"""自动战报推送卡片。"""
from khl.card import Card, CardMessage, Element, Module, Types

from bot.cards.layout import interleave_dividers, kmd_section
from bot.cards.query_cards import beijing, display_time_prefix, fmt


def battle_report_card(report: dict, ai_summary: str | None = None) -> CardMessage:
    battle_id = report.get("battle_id") or "?"
    guild_name = report.get("guild_name") or "本会"
    started = _time_line(report.get("start_time", ""))
    guild_row = report.get("guild_row") or {}
    guild_lines = [
        f"本会 `{guild_name}`　{report.get('guild_players', 0)} 人",
        f"击杀声望 `{fmt(report.get('guild_kill_fame', 0))}`",
    ]
    if guild_row.get("kills") or guild_row.get("deaths"):
        guild_lines.append(f"击杀/阵亡 {guild_row.get('kills', 0)}/{guild_row.get('deaths', 0)}")

    sections = [
        kmd_section(
            "战场概况",
            [
                f"战役 `{battle_id}`",
                started,
                (
                    f"整场 {report.get('total_players', 0)} 人"
                    f"　击杀 {report.get('total_kills', 0)}"
                    f"　总声望 `{fmt(report.get('total_fame', 0))}`"
                ),
            ],
        ),
        kmd_section("本会表现", guild_lines),
    ]
    if ai_summary:
        sections.append(kmd_section("AI 摘要", _summary_lines(ai_summary)))
    sections.extend(
        [
            Module.Section(Element.Text(_entity_block("公会战力榜", report.get("top_guilds") or []), Types.Text.KMD)),
            Module.Section(Element.Text(_entity_block("联盟战力榜", report.get("top_alliances") or []), Types.Text.KMD)),
            Module.Section(Element.Text(_highlight_block(report.get("player_highlights") or {}), Types.Text.KMD)),
        ]
    )

    card = Card(
        Module.Header(f"📯 {guild_name} ZvZ 战报"),
        *interleave_dividers(sections),
    )
    url = report.get("battle_url")
    if url:
        card.append(
            Module.ActionGroup(
                Element.Button("查看 AlbionBB 战报", url, Types.Click.LINK, Types.Theme.PRIMARY)
            )
        )
    return CardMessage(card)


def _summary_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text).splitlines() if line.strip()][:6]


def _time_line(raw: str) -> str:
    ts = (raw or "")[:19].replace("T", " ")
    bj = beijing(raw or "")
    if bj:
        return f"时间 `{ts} UTC`（{display_time_prefix()} {bj}）"
    return f"时间 `{ts}`" if ts else "时间 `?`"


def _entity_block(title: str, rows: list[dict]) -> str:
    lines = [f"**{title}**"]
    for row in rows:
        if row.get("alliance"):
            name = f"{row.get('name')} [{row.get('alliance')}]"
        else:
            name = str(row.get("name") or "?")
        lines.append(
            f"· {name}　{row.get('players', 0)}人"
            f"　击杀/阵亡 {row.get('kills', 0)}/{row.get('deaths', 0)}"
            f"　声望 `{fmt(row.get('kill_fame', 0))}`"
        )
    if len(lines) == 1:
        lines.append("（无数据）")
    return "\n".join(lines)


def _highlight_block(highlights: dict) -> str:
    most_kills = highlights.get("most_kills")
    top_kill_fame = highlights.get("top_kill_fame")
    most_deaths = highlights.get("most_deaths")
    top_death_fame = highlights.get("top_death_fame")
    return "\n".join(
        [
            "**本会高光**",
            _kills_line("击杀最多", most_kills),
            _fame_line("击杀声望最高", top_kill_fame, "kill_fame"),
            _deaths_line("阵亡最多", most_deaths),
            _fame_line("阵亡声望最高", top_death_fame, "death_fame"),
        ]
    )


def _kills_line(label: str, row: dict | None) -> str:
    if not row:
        return f"· {label}：无"
    return (
        f"· {label}：`{row['name']}`　{row.get('kills', 0)} 次"
        f"　声望 `{fmt(row.get('kill_fame', 0))}`"
    )


def _deaths_line(label: str, row: dict | None) -> str:
    if not row:
        return f"· {label}：无"
    return (
        f"· {label}：`{row['name']}`　{row.get('deaths', 0)} 次"
        f"　损失 `{fmt(row.get('death_fame', 0))}`"
    )


def _fame_line(label: str, row: dict | None, key: str) -> str:
    if not row:
        return f"· {label}：无"
    extra = ""
    if key == "kill_fame":
        extra = f"　{row.get('kills', 0)} 次"
    elif key == "death_fame":
        extra = f"　{row.get('deaths', 0)} 次"
    return f"· {label}：`{row['name']}`　`{fmt(row.get(key, 0))}`{extra}"
