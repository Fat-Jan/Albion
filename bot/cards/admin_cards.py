"""管理员相关卡片：公会选择。"""
import json

from khl.card import Card, CardMessage, Element, Module, Types

MAX_CANDIDATES = 5


def guild_select_card(kook_guild_id: str, candidates: list[dict]) -> CardMessage:
    """列候选公会 + [绑定] 按钮。candidates 为已补充会长/联盟/人数的字典。

    字段：Id, Name, Founder, Alliance, Members。点击回推 bind_guild。
    """
    card = Card(Module.Header("选择要绑定的公会（核对会长/联盟避免绑错）"))
    for g in candidates[:MAX_CANDIDATES]:
        name = g.get("Name", "?")
        gid = g.get("Id", "")
        founder = g.get("Founder") or "未知"
        alliance = g.get("Alliance") or "无"
        members = g.get("Members")
        members_txt = f"{members} 人" if members is not None else "人数未知"
        text = (
            f"**{name}**\n"
            f"会长 `{founder}` · 联盟 `{alliance}` · {members_txt}"
        )
        value = json.dumps({"act": "bind_guild", "gid": gid, "kgid": kook_guild_id})
        card.append(
            Module.Section(
                Element.Text(text, Types.Text.KMD),
                Element.Button("绑定", value, Types.Click.RETURN_VAL, Types.Theme.PRIMARY),
            )
        )
        card.append(Module.Divider())
    card.append(Module.Context(Element.Text("只有管理员点击有效。", Types.Text.KMD)))
    return CardMessage(card)
