"""补装相关卡片：选择死亡 + 死亡详情 + 审批申请。"""
import json

from khl.card import Card, CardMessage, Element, Module, Types

from bot.albion import items
from bot.cards.layout import interleave_dividers, kmd_section
from bot.cards.query_cards import (
    KILLBOARD_URL,
    battle_scale_line,
    beijing,
    beijing_datetime,
    fmt,
    scale_label,
    value_lines,
)

# 装备图标展示顺序（killboard 布局）
_EQUIP_SLOTS = ["MainHand", "OffHand", "Head", "Armor", "Shoes", "Cape", "Bag", "Mount", "Potion"]
_STATUS_ZH = {
    "pending": "待审批",
    "approved": "待发放",
    "rejected": "已拒绝",
    "paid": "已发放",
}
_REVIEWER_STATUS_ZH = {
    "pending": "待审批",
    "approved": "已通过",
    "rejected": "已拒绝",
}
REGEAR_REJECT_REASONS = ("非补装范围", "重复申请", "装备/金额异常", "证据不足")
PAYOUT_METHOD_LABELS = {
    "silver": "等额银币",
    "equipment": "原样装备",
    "item": "等价值物品",
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


def _event_summary_lines(event: dict) -> list[str]:
    victim = event.get("Victim") or {}
    killer = event.get("Killer") or {}
    raw = event.get("TimeStamp") or ""
    ts = raw[:19].replace("T", " ")
    bj = beijing(raw)
    when = f"`{ts} UTC`（北京 {bj}）" if bj else f"`{ts}`"
    fame = event.get("TotalVictimKillFame") or 0
    participants = event.get("numberOfParticipants") or len(event.get("Participants") or []) or 1
    lines = [
        f"死亡：{when}　IP `{victim.get('AverageItemPower', 0):.0f}`",
        f"被 `{killer.get('Name', '?')}` [{killer.get('GuildName') or '无'}] 击杀",
        f"击杀声望 `{fmt(fame)}`　参与人数 `{participants}`　事件 `{event.get('EventId') or '-'}`",
    ]
    scale = scale_label(event)
    if scale:
        lines[-1] += f"　{scale}"
    return lines


def _equipment_detail_lines(valuation_result: dict | None) -> list[str]:
    if not valuation_result:
        return []
    lines = value_lines(valuation_result, equip_limit=20, bag_limit=0)
    if not lines:
        return []
    return lines


def _append_killboard_button(card: Card, event_id) -> None:
    if not event_id:
        return
    label = f"查看官方击杀板 #{event_id}"
    card.append(
        Module.ActionGroup(
            Element.Button(
                label,
                KILLBOARD_URL.format(eid=event_id),
                Types.Click.LINK,
                Types.Theme.SECONDARY,
            )
        )
    )


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
                f"查看官方击杀板 #{eid}",
                KILLBOARD_URL.format(eid=eid),
                Types.Click.LINK,
                Types.Theme.SECONDARY,
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
    regear_id: int,
    kook_user_id: str,
    player_name: str,
    event: dict,
    est_value: int,
    valuation_result: dict | None = None,
    ai_hint: str | None = None,
) -> CardMessage:
    """补装审批卡片，发到审批频道。"""
    detail_lines = _equipment_detail_lines(valuation_result)
    pass_val = json.dumps({"act": "regear_approve", "rid": regear_id})
    sections = [
        kmd_section(
            "审核事项",
            [
                f"申请号：`#{regear_id}`",
                f"当前状态：`待审批`",
                f"申请人：(met){kook_user_id}(met)　角色：`{player_name}`",
            ],
        ),
        kmd_section("死亡事件", _event_summary_lines(event)),
        kmd_section(
            "补装口径",
            [
                f"补装金额 ≈ {_silver(est_value)} 银（只计算穿戴装备）",
                "背包物品不计入补装；仅用于死亡详情/损失展示。",
            ],
        ),
    ]
    if ai_hint:
        sections.append(kmd_section("AI 审核提示", _ai_hint_lines(ai_hint)))
    sections.append(kmd_section("装备明细", detail_lines or ["（暂无装备估值明细）"]))
    card = Card(
        *interleave_dividers(sections),
        Module.ActionGroup(
            Element.Button("通过", pass_val, Types.Click.RETURN_VAL, Types.Theme.SUCCESS),
        ),
        Module.Context(Element.Text("管理员或补装审核身份组点击有效；拒绝必须选择理由。", Types.Text.KMD)),
    )
    _append_killboard_button(card, event.get("EventId"))
    card.append(
        Module.ActionGroup(
            *[
                Element.Button(
                    f"拒绝：{reason}",
                    json.dumps({"act": "regear_reject", "rid": regear_id, "reason": reason}, ensure_ascii=False),
                    Types.Click.RETURN_VAL,
                    Types.Theme.DANGER,
                )
                for reason in REGEAR_REJECT_REASONS
            ]
        )
    )
    card.append(Module.Context(Element.Text(f"自定义拒绝理由：`/补装 拒绝 #{regear_id} 理由文本`", Types.Text.KMD)))
    return CardMessage(card)


def _ai_hint_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text).splitlines() if line.strip()][:6]


def regear_reviewer_apply_card(request_id: int, kook_user_id: str) -> CardMessage:
    """补装审核身份申请卡片，仍由管理员审批。"""
    pass_val = json.dumps({"act": "regear_reviewer_approve", "rid": request_id})
    reject_val = json.dumps({"act": "regear_reviewer_reject", "rid": request_id})
    card = Card(
        Module.Section(
            Element.Text(
                f"**补装审核身份申请**\n申请号：`#{request_id}`\n"
                f"当前状态：`待审批`\n申请人：(met){kook_user_id}(met)\n"
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


def regear_reviewer_result_card(req: dict, *, warnings: list[str] | None = None) -> CardMessage:
    """补装审核身份申请结果卡：通知申请人，也用于覆盖原审批卡。"""
    rid = req.get("id") or "?"
    user_id = req.get("kook_user_id") or "?"
    status = req.get("status") or "pending"
    status_zh = _REVIEWER_STATUS_ZH.get(status, status)
    if status == "approved":
        title = f"✅ 补装审核身份申请 `#{rid}` 已通过"
        theme = Types.Theme.SUCCESS
        result_line = "申请已通过，已尝试发放配置的补装审核身份组。"
    elif status == "rejected":
        title = f"❌ 补装审核身份申请 `#{rid}` 已拒绝"
        theme = Types.Theme.DANGER
        result_line = "未发放补装审核身份组。"
    else:
        title = f"补装审核身份申请 `#{rid}` 状态更新"
        theme = Types.Theme.INFO
        result_line = "请等待管理员处理。"
    lines = [
        title,
        f"申请号：`#{rid}`",
        f"申请人：(met){user_id}(met)",
        f"当前状态：`{status_zh}`",
    ]
    if req.get("created_at"):
        lines.append(f"申请时间：`{beijing_datetime(req['created_at'])}`")
    if req.get("reviewed_at"):
        reviewer = req.get("reviewed_by") or "-"
        lines.append(
            f"审核时间：`{beijing_datetime(req['reviewed_at'])}`　审核人：(met){reviewer}(met)"
        )
    lines.append(result_line)
    if warnings:
        lines.append("⚠️ " + "；".join(warnings))
    return CardMessage(Card(Module.Section(Element.Text("\n".join(lines), Types.Text.KMD)), theme=theme))


def regear_approved_card(
    regear_row: dict, event: dict | None = None, valuation_result: dict | None = None
) -> CardMessage:
    """审批通过后的待发放卡片。"""
    rid = regear_row["id"]
    issue_lines = [
        "补装已通过，等待发放",
        f"当前状态：`{_STATUS_ZH.get(regear_row.get('status'), '待发放')}`",
        f"申请人：(met){regear_row['kook_user_id']}(met)",
        f"申请号：`#{rid}`　事件：`{regear_row.get('event_id') or '-'}`",
        f"金额 ≈ `{_silver(regear_row.get('est_value'))}` 银",
    ]
    if regear_row.get("created_at"):
        issue_lines.append(f"申请时间：`{beijing_datetime(regear_row['created_at'])}`")
    if regear_row.get("reviewed_at"):
        reviewed_by = regear_row.get("reviewed_by") or "-"
        issue_lines.append(
            f"审核时间：`{beijing_datetime(regear_row['reviewed_at'])}`　审核人：(met){reviewed_by}(met)"
        )
    issue_lines.append("发放后请选择实际方式，状态会落库为 `paid`。")
    sections = [kmd_section("发放事项", issue_lines)]
    if event:
        sections.append(kmd_section("死亡事件", _event_summary_lines(event)))
    detail_lines = _equipment_detail_lines(valuation_result)
    if detail_lines:
        sections.append(kmd_section("装备明细", detail_lines))
    card = Card(
        *interleave_dividers(sections),
        Module.Context(Element.Text("管理员或补装审核身份组点击有效。", Types.Text.KMD)),
    )
    _append_killboard_button(card, (event or {}).get("EventId") or regear_row.get("event_id"))
    card.append(
        Module.ActionGroup(
            *[
                Element.Button(
                    f"{label}已发放",
                    json.dumps({"act": "regear_paid", "rid": rid, "method": method}),
                    Types.Click.RETURN_VAL,
                    Types.Theme.SUCCESS,
                )
                for method, label in PAYOUT_METHOD_LABELS.items()
            ]
        )
    )
    card.append(Module.Context(Element.Text(f"带备注发放：`/补装 发放 #{rid} 银币|装备|物品 备注`", Types.Text.KMD)))
    return CardMessage(card)


def regear_notice_card(
    regear_row: dict, event: dict | None = None, valuation_result: dict | None = None
) -> CardMessage:
    """补装结果通知卡：给通知频道和处理频道复用。"""
    rid = regear_row.get("id") or "?"
    status = regear_row.get("status")
    status_zh = _STATUS_ZH.get(status, status or "?")
    if status == "rejected":
        title = f"❌ 补装申请 `#{rid}` 已拒绝"
        theme = Types.Theme.DANGER
    elif status == "paid":
        title = f"✅ 补装申请 `#{rid}` 已发放"
        theme = Types.Theme.SUCCESS
    elif status == "approved":
        title = f"✅ 补装申请 `#{rid}` 已通过"
        theme = Types.Theme.SUCCESS
    else:
        title = f"补装申请 `#{rid}` 状态更新"
        theme = Types.Theme.INFO

    issue_lines = [
        title,
        f"申请号：`#{rid}`",
        f"申请人：(met){regear_row.get('kook_user_id') or '?'}(met)",
        f"当前状态：`{status_zh}`",
        f"事件：`{regear_row.get('event_id') or '-'}`",
        f"补装金额 ≈ `{_silver(regear_row.get('est_value'))}` 银",
    ]
    if regear_row.get("created_at"):
        issue_lines.append(f"申请时间：`{beijing_datetime(regear_row['created_at'])}`")
    if regear_row.get("reviewed_at"):
        reviewer = regear_row.get("reviewed_by") or "-"
        issue_lines.append(
            f"审核时间：`{beijing_datetime(regear_row['reviewed_at'])}`　审核人：(met){reviewer}(met)"
        )
    if status == "rejected":
        issue_lines.append(f"原因：`{regear_row.get('reject_reason') or '未填写'}`")
    if status == "paid":
        issue_lines.append(
            f"发放时间：`{beijing_datetime(regear_row.get('paid_at')) or '未知'}`　"
            f"发放人：(met){regear_row.get('paid_by') or '-'}(met)"
        )
        issue_lines.append(f"发放方式：`{PAYOUT_METHOD_LABELS.get(regear_row.get('payout_method') or '', regear_row.get('payout_method') or '未记录')}`")
        if regear_row.get("payout_note"):
            issue_lines.append(f"备注：`{regear_row['payout_note']}`")

    sections = [kmd_section("补装通知", issue_lines)]
    if event:
        sections.append(kmd_section("死亡事件", _event_summary_lines(event)))
    detail_lines = _equipment_detail_lines(valuation_result)
    sections.append(kmd_section("装备明细", detail_lines or ["（暂无装备估值明细）"]))

    card = Card(*interleave_dividers(sections), theme=theme)
    _append_killboard_button(card, (event or {}).get("EventId") or regear_row.get("event_id"))
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
        card.append(
            Module.ActionGroup(
                *[
                    Element.Button(
                        f"#{r['id']} {label}",
                        json.dumps({"act": "regear_paid", "rid": r["id"], "method": method}),
                        Types.Click.RETURN_VAL,
                        Types.Theme.SUCCESS,
                    )
                    for method, label in PAYOUT_METHOD_LABELS.items()
                ]
            )
        )
    return CardMessage(card)
