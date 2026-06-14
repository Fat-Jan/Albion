"""AODP 市场 API 封装（亚服 east）。限流由 client 统一处理。

估值口径走 history（近 N 天 avg_price）；prices 即时价仅给 /物价。
"""
from typing import Iterable, Union

from bot.albion.client import AlbionClient

# 五大皇家城 + 红城；红城（Caerleon）为估值主口径，其余兜底
ROYAL_CITIES = ["Caerleon", "Bridgewatch", "Lymhurst", "Martlock", "Fort Sterling", "Thetford"]


def _join(items: Union[str, Iterable[str]]) -> str:
    if isinstance(items, str):
        return items
    return ",".join(items)


class Market:
    def __init__(self, client: AlbionClient) -> None:
        self.c = client

    async def prices(
        self,
        items: Union[str, Iterable[str]],
        locations: Union[str, Iterable[str], None] = None,
        qualities: Union[str, Iterable[int], None] = None,
    ) -> list:
        """当前最低卖价快照（/物价 用）。"""
        params: dict = {}
        if locations:
            params["locations"] = _join(locations) if not isinstance(locations, str) else locations
        if qualities:
            params["qualities"] = _join([str(q) for q in qualities]) if not isinstance(qualities, str) else qualities
        path = f"/api/v2/stats/prices/{_join(items)}.json"
        return await self.c.aodp_get(path, params=params or None, ttl=300)

    async def history(
        self,
        items: Union[str, Iterable[str]],
        locations: Union[str, Iterable[str], None] = None,
        qualities: Union[str, Iterable[int], None] = None,
        time_scale: int = 24,
    ) -> list:
        """近 N 天历史均价（估值口径）。time-scale 24=按天聚合。"""
        params: dict = {"time-scale": time_scale}
        if locations:
            params["locations"] = locations if isinstance(locations, str) else _join(locations)
        if qualities:
            params["qualities"] = qualities if isinstance(qualities, str) else _join([str(q) for q in qualities])
        path = f"/api/v2/stats/history/{_join(items)}.json"
        return await self.c.aodp_get(path, params=params, ttl=900)

    async def gold(self, count: int = 24) -> list:
        """金价近 count 个数据点。"""
        return await self.c.aodp_get(
            "/api/v2/stats/gold.json", params={"count": count}, ttl=300
        )
