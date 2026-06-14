"""AI 辅助指令：/助手 /战报 /补装解释。

AI 只做只读解释和摘要，不参与审批、发组、改金额或标记发放。
"""
import logging

from khl import Bot, Message

from bot.ai.context import regear_explain_context
from bot.ai.router import AIRouter
from bot.ai.service import AIService
from bot.albion import valuation
from bot.albion.gameinfo import GameInfo
from bot.albion.market import Market
from bot.commands import regear as regear_cmds
from bot import perms
from bot.store import repo

log = logging.getLogger(__name__)


def register(bot: Bot, ai_service: AIService, gi: GameInfo, mk: Market) -> None:
    router = AIRouter(ai_service, gameinfo=gi)

    @bot.command(name="助手")
    async def assistant_cmd(msg: Message, *args):
        question = " ".join(args).strip()
        binding = repo.get_guild_binding(msg.ctx.guild.id)
        can_manage_regear = False
        can_manage_guild = False
        try:
            can_manage_regear = await regear_cmds._can_manage_regear(
                msg.ctx.guild, msg.author, binding
            )
        except Exception as exc:
            log.warning("AI 助手权限探测失败，降级为本人只读范围: %s", exc)
        try:
            can_manage_guild = await perms.is_guild_admin(msg.ctx.guild, msg.author)
        except Exception as exc:
            log.warning("AI 助手管理员权限探测失败，降级为非管理员范围: %s", exc)
        answer = await router.answer(
            msg.ctx.guild.id,
            msg.author.id,
            question,
            can_manage_regear=can_manage_regear,
            can_manage_guild=can_manage_guild,
        )
        await msg.reply(answer)

    @bot.command(name="战报")
    async def battle_report_cmd(msg: Message, *args):
        binding = repo.get_guild_binding(msg.ctx.guild.id)
        if not binding:
            await msg.reply("本服还没绑定公会，请管理员先 /绑定公会。")
            return
        try:
            battles = await gi.battles(guild_id=binding["albion_guild_id"], limit=8)
        except Exception as exc:
            log.warning("战报拉取失败: %s", exc)
            await msg.reply("⚠️ 查询战役失败，稍后再试。")
            return
        text = await ai_service.summarize_battles(binding["albion_guild_name"], battles or [])
        if not text:
            await msg.reply("AI 暂时不可用；可以先用 `/战役` 查看最近战役。")
            return
        await msg.reply(text)

    @bot.command(name="补装解释")
    async def regear_explain_cmd(msg: Message, *args):
        if not args or not str(args[0]).isdigit():
            await msg.reply("用法：`/补装解释 <申请号>`")
            return
        rid = int(args[0])
        rr = repo.get_regear(rid)
        if not rr or rr.get("kook_guild_id") != msg.ctx.guild.id:
            await msg.reply("没有找到这条补装申请。")
            return
        if rr.get("kook_user_id") != msg.author.id:
            gbind = repo.get_guild_binding(msg.ctx.guild.id)
            if not await regear_cmds._can_manage_regear(msg.ctx.guild, msg.author, gbind):
                await msg.reply("⛔ 只有申请人、管理员或补装审核身份组可以查看补装解释。")
                return
        try:
            ev = await gi.event(rr["event_id"])
            result = await valuation.estimate(ev, mk)
        except Exception as exc:
            log.warning("补装解释事实包生成失败: %s", exc)
            await msg.reply("⚠️ 查询补装详情失败，稍后再试。")
            return
        facts = regear_explain_context(rr, ev, result)
        text = await ai_service.explain_regear(facts)
        if not text:
            await msg.reply("AI 暂时不可用；补装金额仍以审批卡片和数据库记录为准。")
            return
        await msg.reply("AI 辅助说明，仅供参考：\n" + text)
