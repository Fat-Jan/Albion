"""玩家绑定相关卡片：待审批。"""
import json

from khl.card import Card, CardMessage, Element, Module, Types


_BIND_STATUS_ZH = {
    "approved": "已通过",
    "rejected": "已拒绝",
    "pending": "待审批",
}


def _display_nickname(player_name: str, custom_nickname: str | None = None) -> str:
    custom = (custom_nickname or "").strip()
    return f"{player_name} - {custom}" if custom else player_name


def approval_card(
    pending_id: int, kook_user_id: str, player: dict, custom_nickname: str | None = None
) -> CardMessage:
    """待审批卡片：角色信息 + 申请人 + [通过]/[拒绝]。

    player 为 gameinfo 搜索条目（含 Name/GuildName/KillFame/DeathFame/FameRatio）。
    """
    name = player.get("Name", "?")
    guild_name = player.get("GuildName") or "无公会"
    kf = player.get("KillFame")
    df = player.get("DeathFame")
    ratio = player.get("FameRatio")
    stats = []
    if kf is not None:
        stats.append(f"击杀声望 {kf:,}")
    if df is not None:
        stats.append(f"死亡声望 {df:,}")
    if ratio is not None:
        stats.append(f"KD {ratio}")
    stats_txt = " · ".join(stats) if stats else "无战斗数据"

    text = (
        f"**绑定申请**\n"
        f"申请号：`#{pending_id}`\n"
        f"当前状态：`待审批`\n"
        f"申请人：(met){kook_user_id}(met)\n"
        f"角色：`{name}`　公会：`{guild_name}`\n"
        f"KOOK 昵称：`{_display_nickname(name, custom_nickname)}`\n"
        f"{stats_txt}"
    )
    pass_val = json.dumps({"act": "approve_bind", "pid": pending_id})
    reject_val = json.dumps({"act": "reject_bind", "pid": pending_id})

    card = Card(
        Module.Section(Element.Text(text, Types.Text.KMD)),
        Module.ActionGroup(
            Element.Button("通过", pass_val, Types.Click.RETURN_VAL, Types.Theme.SUCCESS),
            Element.Button("拒绝", reject_val, Types.Click.RETURN_VAL, Types.Theme.DANGER),
        ),
        Module.Context(Element.Text("只有管理员点击有效。", Types.Text.KMD)),
    )
    return CardMessage(card)


def binding_result_card(pending: dict, *, warnings: list[str] | None = None) -> CardMessage:
    """绑定审批结果卡片：用于成员通知，也用于覆盖原审批卡。"""
    status = pending.get("status") or "pending"
    status_zh = _BIND_STATUS_ZH.get(status, status)
    rid = pending.get("id") or "?"
    user_id = pending.get("kook_user_id") or "?"
    player_name = pending.get("albion_player_name") or "?"
    display_name = _display_nickname(player_name, pending.get("custom_nickname"))
    if status == "approved":
        title = f"✅ 绑定申请 `#{rid}` 已通过"
        theme = Types.Theme.SUCCESS
        result_line = "角色绑定已生效，已按配置发放会员身份组并尝试同步昵称。"
    elif status == "rejected":
        title = f"❌ 绑定申请 `#{rid}` 已拒绝"
        theme = Types.Theme.DANGER
        result_line = "角色绑定未生效，如需重新申请请确认角色信息后再提交。"
    else:
        title = f"绑定申请 `#{rid}` 状态更新"
        theme = Types.Theme.INFO
        result_line = "请等待管理员处理。"
    lines = [
        title,
        f"申请号：`#{rid}`",
        f"申请人：(met){user_id}(met)",
        f"角色：`{player_name}`",
        f"KOOK 昵称：`{display_name}`",
        f"当前状态：`{status_zh}`",
        result_line,
    ]
    if warnings:
        lines.append("⚠️ " + "；".join(warnings))
    return CardMessage(Card(Module.Section(Element.Text("\n".join(lines), Types.Text.KMD)), theme=theme))
