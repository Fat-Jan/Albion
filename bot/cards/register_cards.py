"""玩家绑定相关卡片：待审批。"""
import json

from khl.card import Card, CardMessage, Element, Module, Types


def approval_card(pending_id: int, kook_user_id: str, player: dict) -> CardMessage:
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
        f"申请人：(met){kook_user_id}(met)\n"
        f"角色：`{name}`　公会：`{guild_name}`\n"
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
