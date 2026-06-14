"""补装相关卡片：选择死亡 + 死亡详情 + 审批申请。"""
import json

from khl.card import Card, CardMessage, Element, Module, Types

from bot.albion import items
from bot.cards.query_cards import KILLBOARD_URL, battle_scale_line, beijing, fmt, scale_label, value_lines

# 装备图标展示顺序（killboard 布局）
_EQUIP_SLOTS = ["MainHand", "OffHand", "Head", "Armor", "Shoes", "Cape", "Bag", "Mount", "Potion"]
_STATUS_ZH = {
    "pending": "待审批",
    "approved": "待发放",
    "rejected": "已拒绝",
    "paid": "已发放",
}


def _silver(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "?"


def _estimate_for_event(estimates: dict | None, event_id) -> int | None:
    if not estimates:
        return None
    for key in (event_id, str(event_id)):
        if key in estimates:
            raw = estimates[key]
            if isinstance(raw, dict):
                raw = raw.get("total")
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None
    return None


def _mainhand_line(event: dict) -> str:
    mainhand = (((event.get("Victim") or {}).get("Equipment") or {}).get("MainHand") or {})
    type_ = mainhand.get("Type")
    if not type_:
        return "装备：主手 `无`"
    tier = items.tier_enchant(type_) or "?"
    name = items.localized(type_)
    return f"装备：主手 `{tier}` {name}" if name else f"装备：主手 `{tier}`"


def death_select_card(
    player_name: str, deaths: list, max_n: int = 5, estimates: dict | None = None
) -> CardMessage:
    """列玩家最近死亡，[详情] 看装备明细、[选这个] 发起补装申请。"""
    card = Card(Module.Header(f"{player_name} 最近死亡（详情 / 申请补装）"))
    for ev in deaths[:max_n]:
        eid = ev.get("EventId")
        raw = ev.get("TimeStamp") or ""
        ts = raw[:19].replace("T", " ")
        bj = beijing(raw)
        when = f"`{ts} UTC`（北京 {bj}）" if bj else f"`{ts}`"
        ip = (ev.get("Victim") or {}).get("AverageItemPower", 0)
        killer = (ev.get("Killer") or {}).get("Name", "?")
        scale = scale_label(ev)
        scale_txt = f"　{scale}" if scale else ""
        extra_lines = []
        estimate = _estimate_for_event(estimates, eid)
        if estimate is not None:
            extra_lines.append(f"装备估价 ≈ `{_silver(estimate)}` 银")
        extra_lines.append(_mainhand_line(ev))
        text = (
            f"{when}　IP `{ip:.0f}`{scale_txt}\n"
            f"被 `{killer}` 击杀\n"
            + "\n".join(extra_lines)
        )
        detail_val = json.dumps({"act": "regear_detail", "eid": str(eid)})
        pick_val = json.dumps({"act": "regear_pick", "eid": str(eid)})
        card.append(
            Module.Section(
                Element.Text(text, Types.Text.KMD),
                Element.Button("详情", detail_val, Types.Click.RETURN_VAL, Types.Theme.INFO),
            )
        )
        card.append(
            Module.ActionGroup(
                Element.Button("选这个补装", pick_val, Types.Click.RETURN_VAL, Types.Theme.PRIMARY),
            )
        )
        card.append(Module.Divider())
    return CardMessage(card)


def death_detail_card(
    player_name: str, event: dict, result: dict, battle_players: int = 0
) -> CardMessage:
    """死亡详情卡：击杀方 + 装备明细 + 估值 + 官方击杀板链接。

    battle_players：所属战役总参战人数（调用方查 /battles/{id} 传入）。
    击杀小队小（≤10）但战役大（≥40）→ 推测为 ZvZ 尖刀/炸弹小队。
    """
    eid = event.get("EventId")
    victim = event.get("Victim") or {}
    killer = event.get("Killer") or {}
    fame = event.get("TotalVictimKillFame") or 0
    assists = event.get("numberOfParticipants") or len(event.get("Participants") or []) or 1
    raw = event.get("TimeStamp") or ""
    ts = raw[:19].replace("T", " ")
    bj = beijing(raw)
    when = f"`{ts} UTC`（北京 {bj}）" if bj else f"`{ts}`"
    scale_line = battle_scale_line(event, battle_players)

    head = (
        f"被 `{killer.get('Name', '?')}` [{killer.get('GuildName') or '无'}] 击杀"
        + (f"（{assists} 人参与）" if assists and assists > 1 else "")
        + "\n"
        + f"声望 `{fmt(fame)}`　IP `{victim.get('AverageItemPower', 0):.0f}`"
        + (f"　{scale_line}" if scale_line else "")
        + "\n"
        + when
    )

    lines = [
        f"**补装金额 ≈ {_silver(result['total'])} 银**（只计算穿戴装备）",
        "背包物品不计入补装；仅用于损失展示。",
        "",
    ]
    lines.extend(value_lines(result, equip_limit=10, bag_limit=8))

    card = Card(
        Module.Header(f"💀 {player_name} 死亡详情"),
        Module.Section(Element.Text(head, Types.Text.KMD)),
        theme=Types.Theme.DANGER,
    )
    # 装备图标网格：按穿戴槽位顺序，含品质边框（ImageGroup 限 9 张）
    eq = victim.get("Equipment") or {}
    imgs = []
    for slot in _EQUIP_SLOTS:
        it = eq.get(slot)
        if it and it.get("Type"):
            q = it.get("Quality", 1) or 1
            imgs.append(
                Element.Image(
                    items.render_url(it["Type"], q),
                    alt=items.localized(it["Type"]),
                )
            )
    if imgs:
        card.append(Module.ImageGroup(*imgs[:9]))
    card.append(Module.Divider())
    card.append(Module.Section(Element.Text("\n".join(lines), Types.Text.KMD)))
    card.append(
        Module.ActionGroup(
            Element.Button(
                "查看官方击杀板", KILLBOARD_URL.format(eid=eid), Types.Click.LINK, Types.Theme.SECONDARY
            ),
            Element.Button(
                "选这个补装",
                json.dumps({"act": "regear_pick", "eid": str(eid)}),
                Types.Click.RETURN_VAL,
                Types.Theme.PRIMARY,
            ),
        )
    )
    return CardMessage(card)


def regear_apply_card(
    regear_id: int, kook_user_id: str, player_name: str, event: dict, est_value: int
) -> CardMessage:
    """补装审批卡片，发到审批频道。"""
    ts = (event.get("TimeStamp") or "")[:19].replace("T", " ")
    ip = (event.get("Victim") or {}).get("AverageItemPower", 0)
    text = (
        f"**补装申请**\n"
        f"申请人：(met){kook_user_id}(met)　角色：`{player_name}`\n"
        f"死亡：`{ts}`　IP `{ip:.0f}`\n"
        f"**补装金额 ≈ {_silver(est_value)} 银**（只计算穿戴装备）\n"
        f"背包物品不计入补装；仅用于死亡详情/损失展示。"
    )
    pass_val = json.dumps({"act": "regear_approve", "rid": regear_id})
    reject_val = json.dumps({"act": "regear_reject", "rid": regear_id})
    card = Card(
        Module.Section(Element.Text(text, Types.Text.KMD)),
        Module.ActionGroup(
            Element.Button("通过", pass_val, Types.Click.RETURN_VAL, Types.Theme.SUCCESS),
            Element.Button("拒绝", reject_val, Types.Click.RETURN_VAL, Types.Theme.DANGER),
        ),
        Module.Context(Element.Text("管理员或补装审核身份组点击有效。", Types.Text.KMD)),
    )
    return CardMessage(card)


def regear_reviewer_apply_card(request_id: int, kook_user_id: str) -> CardMessage:
    """补装审核身份申请卡片，仍由管理员审批。"""
    pass_val = json.dumps({"act": "regear_reviewer_approve", "rid": request_id})
    reject_val = json.dumps({"act": "regear_reviewer_reject", "rid": request_id})
    card = Card(
        Module.Section(
            Element.Text(
                f"**补装审核身份申请**\n申请人：(met){kook_user_id}(met)\n"
                "通过后会自动授予已配置的补装审核身份组。",
                Types.Text.KMD,
            )
        ),
        Module.ActionGroup(
            Element.Button("通过", pass_val, Types.Click.RETURN_VAL, Types.Theme.SUCCESS),
            Element.Button("拒绝", reject_val, Types.Click.RETURN_VAL, Types.Theme.DANGER),
        ),
        Module.Context(Element.Text("只有管理员可以审批补装审核身份。", Types.Text.KMD)),
    )
    return CardMessage(card)


def regear_approved_card(regear_row: dict) -> CardMessage:
    """审批通过后的待发放卡片。"""
    rid = regear_row["id"]
    text = (
        f"**补装已通过，等待发放**\n"
        f"申请人：(met){regear_row['kook_user_id']}(met)\n"
        f"申请号：`#{rid}`　事件：`{regear_row.get('event_id') or '-'}`\n"
        f"金额 ≈ `{fmt(regear_row.get('est_value'))}` 银\n"
        f"发放银币/物资后点击下方按钮，状态会落库为 `paid`。"
    )
    paid_val = json.dumps({"act": "regear_paid", "rid": rid})
    card = Card(
        Module.Section(Element.Text(text, Types.Text.KMD)),
        Module.ActionGroup(
            Element.Button("标记已发放", paid_val, Types.Click.RETURN_VAL, Types.Theme.SUCCESS),
        ),
        Module.Context(Element.Text("管理员或补装审核身份组点击有效。", Types.Text.KMD)),
    )
    return CardMessage(card)


def regear_queue_card(title: str, rows: list[dict]) -> CardMessage:
    """管理员查看补装 SQL 队列。"""
    lines = [f"**{title}**"]
    if not rows:
        lines.append("暂无记录。")
    for r in rows:
        status = _STATUS_ZH.get(r.get("status"), r.get("status") or "?")
        lines.append(
            f"· `#{r['id']}` {status}　(met){r['kook_user_id']}(met)　"
            f"金额 `{fmt(r.get('est_value'))}`　事件 `{r.get('event_id') or '-'}`"
        )
    card = Card(Module.Section(Element.Text("\n".join(lines), Types.Text.KMD)))
    for r in rows[:5]:
        if r.get("status") != "approved":
            continue
        paid_val = json.dumps({"act": "regear_paid", "rid": r["id"]})
        card.append(
            Module.ActionGroup(
                Element.Button(
                    f"标记 #{r['id']} 已发放",
                    paid_val,
                    Types.Click.RETURN_VAL,
                    Types.Theme.SUCCESS,
                )
            )
        )
    return CardMessage(card)
