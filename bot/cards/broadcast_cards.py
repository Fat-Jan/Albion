"""死亡播报卡片：我方击杀 / 我方阵亡，大额高亮。"""
from khl.card import Card, CardMessage, Element, Module, Types

from bot.albion import valuation
from bot.cards.query_cards import KILLBOARD_URL
from bot.cards.query_cards import beijing, fmt, scale_label


def kill_card(
    event: dict,
    is_kill: bool,
    highlight: bool,
    valuation_result: dict | None = None,
) -> CardMessage:
    """is_kill=True 我方击杀（绿），False 我方阵亡（红）；highlight 大额加金色头。"""
    killer = event.get("Killer") or {}
    victim = event.get("Victim") or {}
    fame = event.get("TotalVictimKillFame") or 0
    raw = event.get("TimeStamp") or ""
    ts = raw[:19].replace("T", " ")
    bj = beijing(raw)
    when = f"`{ts} UTC`（北京 {bj}）" if bj else f"`{ts}`"
    victim_ip = victim.get("AverageItemPower", 0)
    scale = scale_label(event)

    if is_kill:
        title = "💚 我方击杀" + ("　💰 大额！" if highlight else "")
        theme = Types.Theme.WARNING if highlight else Types.Theme.SUCCESS
    else:
        title = "💀 我方阵亡" + ("　⚠️ 大额损失！" if highlight else "")
        theme = Types.Theme.WARNING if highlight else Types.Theme.DANGER

    text = (
        f"`{killer.get('Name', '?')}` [{killer.get('GuildName') or '无'}]\n"
        f"⚔️ 击杀 `{victim.get('Name', '?')}` [{victim.get('GuildName') or '无'}]\n"
        f"声望 `{fmt(fame)}`　受害者 IP `{victim_ip:.0f}`"
        + (f"　{scale}" if scale else "")
        + "\n"
        + when
    )

    if not is_kill and valuation_result:
        sums = valuation.summary(valuation_result)
        text += (
            "\n"
            f"装备估值 `{fmt(sums['equipment_total'])}` 银　"
            f"背包估值 `{fmt(sums['inventory_total'])}` 银　"
            f"总损失 `{fmt(sums['loss_total'])}` 银"
        )

    card = Card(
        Module.Header(title),
        Module.Section(Element.Text(text, Types.Text.KMD)),
        theme=theme,
    )
    eid = event.get("EventId")
    if eid:
        card.append(
            Module.ActionGroup(
                Element.Button(
                    "查看官方击杀板",
                    KILLBOARD_URL.format(eid=eid),
                    Types.Click.LINK,
                    Types.Theme.SECONDARY,
                )
            )
        )
    return CardMessage(card)
