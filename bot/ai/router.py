"""窄白名单自然语言路由：只读查询可以转工具，写操作一律拒绝。"""
from __future__ import annotations

import logging
import re

from bot.ai.context import (
    binding_status_context,
    guild_config_context,
    player_recent_activity_context,
    regear_status_context,
)
from bot.ai.service import AIService
from bot.store import repo

log = logging.getLogger(__name__)

MUTATING_PHRASES = (
    "帮我通过",
    "给我通过",
    "批准",
    "拒绝",
    "发身份组",
    "发组",
    "撤身份组",
    "撤组",
    "改金额",
    "改成",
    "标记已发放",
    "标成已发放",
    "设为已发放",
    "确认发放",
    "帮我发放",
    "删除绑定",
    "解绑他",
)

REGEAR_STATUS_WORDS = (
    "补装状态",
    "补装进度",
    "补装申请",
    "补装队列",
    "补装概况",
    "补装列表",
    "待发放",
    "待审批",
    "我的补装",
)
BINDING_STATUS_WORDS = ("绑定状态", "我的绑定", "已绑定", "是否绑定", "绑定了谁", "绑了谁")
GUILD_CONFIG_WORDS = ("频道配置", "配置概况", "当前设置", "设置概况", "机器人配置", "配置状态")
RECENT_ACTIVITY_WORDS = (
    "最近死亡",
    "最近阵亡",
    "近期死亡",
    "近期阵亡",
    "最近击杀",
    "近期击杀",
    "最近战绩",
    "近期战绩",
)


class AIRouter:
    def __init__(self, service: AIService, gameinfo=None) -> None:
        self.service = service
        self.gameinfo = gameinfo

    async def answer(
        self,
        guild_id: str,
        user_id: str,
        question: str,
        *,
        can_manage_regear: bool = False,
        can_manage_guild: bool = False,
    ) -> str:
        q = (question or "").strip()
        if not q:
            return "用法：`/助手 <问题>`，例：`/助手 我怎么绑定角色`。"
        if _looks_mutating(q):
            return (
                "我不能执行审批、发身份组、改金额或发放状态这类写操作。"
                "请用对应卡片按钮或管理员命令处理。"
            )
        if _is_binding_status_query(q):
            facts = binding_status_context(
                repo.get_guild_binding(guild_id),
                repo.get_player_binding(user_id, guild_id),
                repo.get_open_pending(user_id, guild_id),
            )
            text = await self.service.answer_readonly_query(q, facts)
            return text or _format_binding_status_fallback(facts)
        if _is_guild_config_query(q):
            if not can_manage_guild:
                return "只有管理员可以查看频道配置概况。"
            facts = guild_config_context(repo.get_guild_binding(guild_id))
            text = await self.service.answer_readonly_query(q, facts)
            return text or _format_guild_config_fallback(facts)
        if _is_recent_activity_query(q):
            return await self._answer_recent_activity(guild_id, user_id, q)
        if _is_regear_status_query(q):
            own_only = (not can_manage_regear) or "我" in q or "我的" in q
            rows = repo.list_regear(guild_id, limit=20 if own_only else 10)
            if own_only:
                rows = [r for r in rows if r.get("kook_user_id") == user_id]
                rows = rows[:10]
            facts = regear_status_context(rows, own_only=own_only)
            text = await self.service.answer_readonly_query(q, facts)
            return text or _format_regear_status_fallback(facts)
        text = await self.service.guide_command(q)
        return text or "AI 暂时不可用。可先试 `/绑定`、`/战绩`、`/估值`、`/补装` 等命令。"

    async def _answer_recent_activity(self, guild_id: str, user_id: str, question: str) -> str:
        binding = repo.get_player_binding(user_id, guild_id)
        if not binding:
            return "你还没有绑定角色。可先用 `/绑定 <角色名>` 发起绑定。"
        if not self.gameinfo:
            return "玩家最近击杀/阵亡查询暂时不可用，可先用 `/战绩` 查看概况。"
        player_id = binding.get("albion_player_id")
        try:
            player = await self.gameinfo.player(player_id)
            kills = await self.gameinfo.player_kills(player_id)
            deaths = await self.gameinfo.player_deaths(player_id)
        except Exception as exc:
            log.warning("AI 最近战绩事实包生成失败: %s", exc)
            return "玩家最近击杀/阵亡查询失败，稍后再试。"
        facts = player_recent_activity_context(player, kills, deaths)
        text = await self.service.answer_readonly_query(question, facts)
        return text or _format_recent_activity_fallback(facts)


def _looks_mutating(question: str) -> bool:
    if any(w in question for w in MUTATING_PHRASES):
        return True
    action_to_request = r"(通过|批准|拒绝)\s*(#?\d+|.*(补装|申请))"
    imperative_action = r"(帮我|给我|把|将).*(通过|批准|拒绝|发放|改金额|改成|标记)"
    return bool(re.search(action_to_request, question) or re.search(imperative_action, question))


def _is_regear_status_query(question: str) -> bool:
    return any(w in question for w in REGEAR_STATUS_WORDS)


def _is_binding_status_query(question: str) -> bool:
    return any(w in question for w in BINDING_STATUS_WORDS)


def _is_guild_config_query(question: str) -> bool:
    return any(w in question for w in GUILD_CONFIG_WORDS)


def _is_recent_activity_query(question: str) -> bool:
    return any(w in question for w in RECENT_ACTIVITY_WORDS)


def _format_binding_status_fallback(facts: dict) -> str:
    if not (facts.get("guild_binding") or {}).get("configured"):
        return "本服还没绑定公会，请管理员先 `/绑定公会 <公会名>`。"
    binding = facts.get("player_binding")
    if binding:
        name = binding.get("albion_player_name") or "未知角色"
        status = binding.get("status") or "verified"
        return f"绑定状态：你已绑定 `{name}`（状态 `{status}`）。"
    pending = facts.get("pending_approval")
    if pending:
        name = pending.get("albion_player_name") or "未知角色"
        return f"绑定状态：`{name}` 正在待审批。"
    return "绑定状态：你还没有绑定角色。可用 `/绑定 <角色名>` 发起绑定。"


def _format_guild_config_fallback(facts: dict) -> str:
    if not (facts.get("guild_binding") or {}).get("configured"):
        return "本服还没绑定公会，请管理员先 `/绑定公会 <公会名>`。"
    s = facts.get("settings") or {}
    lines = ["配置概况："]
    lines.append(f"· 会员身份组：{_configured_text(s.get('member_role_id'))}")
    lines.append(f"· 审批频道：{_configured_text(s.get('approval_channel_id'))}")
    lines.append(f"· 补装申请频道：{_configured_text(s.get('regear_apply_channel_id'))}")
    lines.append(f"· 补装审核频道：{_configured_text(s.get('regear_review_channel_id'))}")
    lines.append(f"· 补装发放频道：{_configured_text(s.get('regear_payout_channel_id'))}")
    lines.append(f"· 补装通知频道：{_configured_text(s.get('regear_notify_channel_id'))}")
    lines.append(f"· 旧补装频道兜底：{_configured_text(s.get('regear_channel_id'))}")
    lines.append(f"· 播报频道：{_configured_text(s.get('broadcast_channel_id'))}")
    lines.append(f"· 补装审核身份组：{int(s.get('regear_reviewer_role_count') or 0)} 个")
    lines.append(f"· 可信身份组：{int(s.get('trusted_role_count') or 0)} 个")
    lines.append(f"· 大额阈值：{int(s.get('kill_fame_threshold') or 100000):,} fame")
    return "\n".join(lines)


def _format_regear_status_fallback(facts: dict) -> str:
    rows = facts.get("requests") or []
    if not rows:
        return "没有查到相关补装申请。"
    lines = ["补装申请："]
    for r in rows[:5]:
        lines.append(
            f"· #{r.get('id')} `{r.get('status')}` 金额 `{int(r.get('est_value') or 0):,}` 银"
        )
    return "\n".join(lines)


def _format_recent_activity_fallback(facts: dict) -> str:
    player = facts.get("player") or {}
    deaths = facts.get("recent_deaths") or []
    kills = facts.get("recent_kills") or []
    lines = [f"最近战绩：`{player.get('name') or '未知角色'}`"]
    if deaths:
        d = deaths[0]
        t = d.get("time") or {}
        lines.append(
            f"· 最近阵亡 #{d.get('event_id')}，{t.get('server_time_utc') or '服务器/API 时间未知'}"
        )
    if kills:
        k = kills[0]
        t = k.get("time") or {}
        lines.append(
            f"· 最近击杀 #{k.get('event_id')}，{t.get('server_time_utc') or '服务器/API 时间未知'}"
        )
    if len(lines) == 1:
        lines.append("· 最近 10 条击杀/阵亡里没有记录。")
    return "\n".join(lines)


def _configured_text(value: object) -> str:
    if isinstance(value, dict):
        return "已设置" if value.get("configured") else "未设置"
    return "已设置" if value else "未设置"
