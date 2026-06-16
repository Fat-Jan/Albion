"""死亡播报卡片：我方击杀 / 我方阵亡，大额高亮。"""
from khl.card import Card, CardMessage, Element, Module, Types

from bot.albion import items, valuation
from bot.cards.query_cards import KILLBOARD_URL
from bot.cards.query_cards import beijing, display_time_prefix, fmt, scale_label


def _ip(actor: dict) -> str:
    try:
        return f"{float(actor.get('AverageItemPower') or 0):.0f}"
    except (TypeError, ValueError):
        return "?"


def _mainhand_text(label: str, actor: dict) -> str:
    mainhand = ((actor.get("Equipment") or {}).get("MainHand") or {})
    type_ = mainhand.get("Type")
    if not type_:
        return f"{label}：`无`"
    tier = items.tier_enchant(type_)
    name = items.localized(type_) or type_
    if tier:
        return f"{label}：`{tier}` {name}"
    return f"{label}：{name}"


def _actor_name(actor: dict) -> str:
    return f"`{actor.get('Name', '?')}` [{actor.get('GuildName') or '无'}]"


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
    title_time = f"　{display_time_prefix()} {bj}" if bj else ""
    when = f"`{ts} UTC`" if bj else f"`{ts}`"
    scale = scale_label(event)

    if is_kill:
        title = "💚 我方击杀" + title_time + ("　💰 大额！" if highlight else "")
        theme = Types.Theme.WARNING if highlight else Types.Theme.SUCCESS
    else:
        title = "💀 我方阵亡" + title_time + ("　⚠️ 大额损失！" if highlight else "")
        theme = Types.Theme.WARNING if highlight else Types.Theme.DANGER

    event_lines = [
        "**事件**",
        "击杀声望 `" + fmt(fame) + "`" + (f"　{scale}" if scale else ""),
        f"时间 {when}",
    ]
    sections = [
        Module.Section(
            Element.Text(
                "\n".join(
                    [
                        "**对阵**",
                        f"{_actor_name(killer)}　→　{_actor_name(victim)}",
                        f"击杀方 IP `{_ip(killer)}`　受害方 IP `{_ip(victim)}`",
                    ]
                ),
                Types.Text.KMD,
            )
        ),
        Module.Divider(),
        Module.Section(Element.Text("\n".join(event_lines), Types.Text.KMD)),
        Module.Divider(),
        Module.Section(
            Element.Text(
                "\n".join(
                    [
                        "**装备**",
                        _mainhand_text("击杀方", killer),
                        _mainhand_text("受害方", victim),
                    ]
                ),
                Types.Text.KMD,
            )
        ),
    ]

    if not is_kill and valuation_result:
        sums = valuation.summary(valuation_result)
        sections.extend(
            [
                Module.Divider(),
                Module.Section(
                    Element.Text(
                        "\n".join(
                            [
                                "**损失估值**",
                                (
                                    f"装备 `{fmt(sums['equipment_total'])}` 银　"
                                    f"背包 `{fmt(sums['inventory_total'])}` 银"
                                ),
                                f"总损失 `{fmt(sums['loss_total'])}` 银",
                            ]
                        ),
                        Types.Text.KMD,
                    )
                ),
            ]
        )

    card = Card(
        Module.Header(title),
        *sections,
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
