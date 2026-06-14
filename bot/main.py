"""机器人入口：khl.py Bot 启动 + WebSocket 连接。

按里程碑在 commands/ 注册指令。共享一个 AlbionClient（带缓存/限流）。
"""
import logging

from khl import Bot, Message

from bot import config
from bot.albion.client import AlbionClient
from bot.albion.gameinfo import GameInfo
from bot.albion.market import Market
from bot.commands import admin, query, regear, register
from bot.store.db import init_db
from bot.tasks import auto

log = logging.getLogger(__name__)


def build_bot() -> Bot:
    config.setup_logging()
    init_db()

    bot = Bot(token=config.require_token())
    client = AlbionClient()
    gi = GameInfo(client)
    mk = Market(client)

    @bot.command(name="ping")
    async def ping(msg: Message):
        await msg.reply("pong")

    admin.register(bot, gi)
    register.register(bot, gi)
    query.register(bot, gi, mk)
    regear.register(bot, gi, mk)
    auto.register(bot, gi, mk)

    return bot


def main() -> None:
    bot = build_bot()
    log.info("机器人启动，连接 KOOK WebSocket...")
    bot.run()


if __name__ == "__main__":
    main()
