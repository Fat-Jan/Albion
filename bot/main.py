"""机器人入口：khl.py Bot 启动 + WebSocket 连接。

按里程碑在 commands/ 注册指令。共享一个 AlbionClient（带缓存/限流）。
"""
import logging

from khl import Bot, Message

from bot import config, region_scope
from bot.ai.client import AIClient, AIClientConfig
from bot.ai.service import AIService
from bot.albion.client import AlbionClient
from bot.albion.gameinfo import GameInfo
from bot.albion.market import Market
from bot.commands import admin, ai, query, regear, register
from bot.store.db import init_db
from bot.tasks import auto
from bot.version import __version__

log = logging.getLogger(__name__)


def ping_text() -> str:
    return f"pong v{__version__}"


def build_bot() -> Bot:
    config.setup_logging()
    init_db()

    bot = Bot(token=config.require_token())
    client = AlbionClient()
    gi = GameInfo(client)
    mk = Market(client)
    ai_client = (
        AIClient(AIClientConfig.from_env())
        if config.AI_ENABLED and config.AI_API_KEY
        else None
    )
    ai_service = AIService(ai_client, enabled=config.AI_ENABLED)

    @bot.command(name="ping")
    async def ping(msg: Message):
        if not region_scope.should_process_message(msg):
            return
        await msg.reply(ping_text())

    admin.register(bot, gi)
    register.register(bot, gi)
    query.register(bot, gi, mk)
    regear.register(bot, gi, mk, ai_service)
    ai.register(bot, ai_service, gi, mk)
    auto.register(bot, gi, mk, ai_service)

    return bot


def main() -> None:
    bot = build_bot()
    token_info = config.token_runtime_info()
    log.info(
        "机器人启动，连接 KOOK WebSocket... bot_id=%s token_fp=%s token_source=%s",
        token_info["bot_id"],
        token_info["fingerprint"],
        token_info["source"],
    )
    bot.run()


if __name__ == "__main__":
    main()
