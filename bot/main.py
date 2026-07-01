"""机器人入口：khl.py Bot 启动 + WebSocket 连接。

按里程碑在 commands/ 注册指令。共享一个 AlbionClient（带缓存/限流）。
"""
import logging
import os
import threading
import asyncio
from http.server import ThreadingHTTPServer

from khl import Bot, Message

from bot import config, region_scope
from bot.ai.client import AIClient, AIClientConfig
from bot.ai.service import AIService
from bot.albion.client import AlbionClient
from bot.albion.gameinfo import GameInfo
from bot.albion.market import Market
from bot.commands import admin, ai, query, regear, register
from bot.store.bootstrap import seed_runtime_guild_config
from bot.store.db import init_db
from bot.tasks import auto
from bot.version import __version__
from bot.web.status_api import StatusAPIHandler

log = logging.getLogger(__name__)


def _configured_health_port() -> int | None:
    for key in ("HEALTH_PORT", "PORT"):
        raw = os.getenv(key, "").strip()
        if not raw:
            continue
        try:
            port = int(raw)
        except ValueError:
            continue
        if 0 < port < 65536:
            return port
    return None


def start_health_server_if_configured() -> ThreadingHTTPServer | None:
    port = _configured_health_port()
    if port is None:
        return None

    server = ThreadingHTTPServer(("0.0.0.0", port), StatusAPIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log.info("health endpoint listening on :%s/healthz", port)
    return server


def ping_text() -> str:
    return f"pong v{__version__}"


def _build_ai_service() -> AIService:
    ai_client = (
        AIClient(AIClientConfig.from_env())
        if config.AI_ENABLED and config.AI_API_KEY
        else None
    )
    return AIService(ai_client, enabled=config.AI_ENABLED)


def _build_region_bot(
    region_code: str, region_cfg: config.AlbionRegionConfig, ai_service: AIService
) -> Bot:
    bot = Bot(token=region_cfg.kook_token)
    setattr(bot, "_region", region_code)
    client = AlbionClient(
        gameinfo_base=region_cfg.gameinfo_base,
        aodp_base=region_cfg.aodp_base,
        albionbb_base=region_cfg.albionbb_base,
    )
    gi = GameInfo(client)
    mk = Market(client)

    @bot.command(name="ping")
    async def ping(msg: Message):
        if not region_scope.should_process_message(msg, region=region_code):
            return
        await msg.reply(ping_text())

    admin.register(bot, gi, region=region_code)
    register.register(bot, gi, region=region_code)
    query.register(bot, gi, mk, region=region_code)
    regear.register(bot, gi, mk, ai_service, region=region_code)
    ai.register(bot, ai_service, gi, mk, region=region_code)
    auto.register(bot, gi, mk, ai_service, region=region_code)
    return bot


def build_bots() -> list[Bot]:
    config.setup_logging()
    init_db()
    ai_service = _build_ai_service()
    bots: list[Bot] = []
    for region_code, region_cfg in config.REGION_CONFIGS.items():
        if not region_cfg.kook_token:
            log.warning("skip region=%s because KOOK token is missing", region_code)
            continue
        seed_runtime_guild_config(region_code)
        bots.append(_build_region_bot(region_code, region_cfg, ai_service))
    if not bots:
        config.require_token()
    return bots


def build_bot() -> Bot:
    bots = build_bots()
    if not bots:
        raise RuntimeError("缺少 KOOK_TOKEN_EU/KOOK_TOKEN_ASIA（见 .env.example）")
    return bots[0]


def main() -> None:
    bots = build_bots()
    start_health_server_if_configured()
    for bot in bots:
        region_code = getattr(bot, "_region", "unknown")
        region_cfg = config.REGION_CONFIGS.get(region_code)
        token_info = config.token_runtime_info(region_cfg.kook_token if region_cfg else "")
        log.info(
            "机器人启动，连接 KOOK WebSocket... region=%s bot_id=%s token_fp=%s token_source=%s",
            region_code,
            token_info["bot_id"],
            token_info["fingerprint"],
            token_info["source"],
        )

    async def run_all() -> None:
        await asyncio.gather(*(bot.start() for bot in bots))

    asyncio.run(run_all())


if __name__ == "__main__":
    main()
