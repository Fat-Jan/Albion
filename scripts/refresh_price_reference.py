"""手动刷新 T4-T8 武器/副手低价参考。"""
import asyncio
import logging

from bot import config
from bot.albion.client import AlbionClient
from bot.albion.market import Market
from bot.albion.price_reference import refresh_weapon_price_reference
from bot.store.db import init_db


async def _main() -> None:
    config.setup_logging()
    logging.getLogger(__name__).info("开始刷新武器/副手低价参考...")
    init_db()
    client = AlbionClient()
    try:
        market = Market(client)
        stats = await refresh_weapon_price_reference(market)
    finally:
        await client.aclose()
    print(
        "刷新完成: "
        f"items={stats['items']} api_rows={stats['api_rows']} records={stats['records']}"
    )


if __name__ == "__main__":
    asyncio.run(_main())
