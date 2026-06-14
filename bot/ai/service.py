"""AI 业务服务：生成短说明，失败时返回空串，不阻断主流程。"""
from __future__ import annotations

import json
import logging
import re
from typing import Protocol

from bot.ai.context import battles_context

log = logging.getLogger(__name__)


class CompletionClient(Protocol):
    async def complete(
        self, messages: list[dict[str, str]], *, max_tokens: int | None = None
    ) -> str:
        ...


SYSTEM_POLICY = (
    "你是 Albion Online 亚服单公会 KOOK 机器人里的 AI 辅助说明层。"
    "你只能解释、总结和引导，不能批准绑定、不能批准补装、不能改写补装金额、"
    "不能撤销或发放身份组、不能标记补装已发放。"
    "所有金额、状态和权限以事实包为准。回答使用简洁中文，最多 8 行。"
    "凡是回复里出现时间，必须注明时间口径：服务器/API 时间 UTC、数据库/服务器时间 UTC，"
    "或北京时间 UTC+8；不要输出未标注的时间。"
)

SECRET_PATTERNS = (
    re.compile(r"KOOK_TOKEN\s*=\s*[^\s，,;]+", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"ak_[A-Za-z0-9]{16,}"),
)

UNSAFE_ACTION_PATTERNS = (
    re.compile(r"(^|[，。；;、\s])(?:我|本助手|助手|AI)?(?:已经|已)(?:批准|通过|拒绝)\s*#?\d+"),
    re.compile(r"(^|[，。；;、\s])(?:我|本助手|助手|AI)?(?:已经|已)(?:批准|通过|拒绝)了"),
    re.compile(r"(?:我|本助手|助手|AI).*(?:已经|已)(?:批准|通过|拒绝|发放)"),
    re.compile(r"(?:已经|已)(?:发身份组|发组|撤组|撤销身份组|改金额|标记)"),
    re.compile(r"金额已(?:改|更新|修改)"),
    re.compile(r"(?:已经|已)发放\s*#?\d+"),
)

READONLY_BOUNDARY_REPLY = (
    "只读说明：AI 只能基于事实包做查询说明，不能批准、拒绝、发组、"
    "撤组、改金额或标记发放。请使用对应卡片按钮或管理员命令处理。"
)


class AIService:
    def __init__(self, client: CompletionClient | None, *, enabled: bool) -> None:
        self.client = client
        self.enabled = enabled and client is not None

    async def _complete(self, user_prompt: str, *, max_tokens: int) -> str:
        if not self.enabled or not self.client:
            return ""
        messages = [
            {"role": "system", "content": SYSTEM_POLICY},
            {"role": "user", "content": user_prompt},
        ]
        try:
            text = await self.client.complete(messages, max_tokens=max_tokens)
        except Exception as exc:
            log.warning("AI 生成失败: %s", exc)
            return ""
        return _sanitize_output(text)

    async def guide_command(self, question: str) -> str:
        prompt = (
            "只回答 KOOK 机器人命令引导，不要编造不存在的命令。"
            "成员常用命令：/绑定 <角色名>、/解绑、/战绩 [角色名]、/估值 [角色名]、"
            "/战役、/物价 <物品名>、/金价、/榜单 pvp|pve、/补装、/补装审核。"
            "管理员命令：/绑定公会 <公会名>、/设置 ...、/补装 待处理、/补装 待发放、/补装 列表。"
            "不要说 /设置 可以查看绑定状态；不知道时建议查看 README 或使用具体命令。"
            "不能批准、不能代替管理员点击、不能声称已经修改任何状态。\n"
            f"用户问题：{question}"
        )
        return await self._complete(prompt, max_tokens=300)

    async def explain_regear(self, facts: dict) -> str:
        prompt = (
            "请基于下面 JSON 事实包解释这条补装申请。"
            "重点说明：补装金额只按穿戴装备、背包仅展示损失、缺价或估值异常。"
            "不得修改金额，不得给出批准/拒绝结论，只能给管理员参考。\n"
            "如果提到时间，优先同时写出服务器/API 时间 UTC 和北京时间 UTC+8。\n"
            f"JSON 事实包：{json.dumps(facts, ensure_ascii=False, separators=(',', ':'))}"
        )
        return await self._complete(prompt, max_tokens=450)

    async def summarize_battles(self, guild_name: str, battles: list[dict]) -> str:
        facts = battles_context(guild_name, battles)
        prompt = (
            "请基于下面 JSON 事实包生成公会战报摘要。"
            "只总结趋势、活跃度和可观察事实，不要编造地图、战术或 API 未提供的信息。\n"
            "如果提到时间，优先同时写出服务器/API 时间 UTC 和北京时间 UTC+8。\n"
            f"JSON 事实包：{json.dumps(facts, ensure_ascii=False, separators=(',', ':'))}"
        )
        return await self._complete(prompt, max_tokens=650)

    async def answer_readonly_query(self, question: str, facts: dict) -> str:
        prompt = (
            "请基于下面 JSON 事实包回答用户的只读查询。"
            "事实包必须来自白名单工具，带 schema_version 和 tool；不要引用事实包以外的数据。"
            "不能执行审批、发组、撤组、改金额、写库等操作；如果用户要求写操作，要拒绝并说明可用命令。\n"
            "如果提到时间，必须标注是服务器/API 时间 UTC、数据库/服务器时间 UTC，还是北京时间 UTC+8。\n"
            f"用户问题：{question}\n"
            f"JSON 事实包：{json.dumps(facts, ensure_ascii=False, separators=(',', ':'))}"
        )
        return await self._complete(prompt, max_tokens=450)


def _sanitize_output(text: str) -> str:
    safe = text or ""
    for pattern in SECRET_PATTERNS:
        safe = pattern.sub("[REDACTED]", safe)
    if any(pattern.search(safe) for pattern in UNSAFE_ACTION_PATTERNS):
        return READONLY_BOUNDARY_REPLY
    return safe
