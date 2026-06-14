"""官方 Gameinfo API 封装（亚服 gameinfo-sgp）。

要点：玩家/公会先 /search 拿 base64 ID 再查详情。只实现机器人用得到的端点。
"""
from typing import Any, Optional

from bot.albion.client import AlbionClient


class GameInfo:
    def __init__(self, client: AlbionClient) -> None:
        self.c = client

    # --- 搜索 ---
    async def search(self, q: str) -> dict:
        """返回 {players:[{Id,Name,...}], guilds:[{Id,Name,...}]}。"""
        return await self.c.gameinfo_get("/search", params={"q": q}, ttl=120)

    async def find_player(self, name: str) -> Optional[dict]:
        """按名精确匹配玩家（忽略大小写），命中返回搜索条目，否则 None。"""
        data = await self.search(name)
        low = name.lower()
        for p in data.get("players", []):
            if p.get("Name", "").lower() == low:
                return p
        return None

    async def find_guild(self, name: str) -> list[dict]:
        """按名搜公会，返回候选列表（供管理员按钮选中）。"""
        data = await self.search(name)
        return data.get("guilds", [])

    # --- 玩家 ---
    async def player(self, player_id: str) -> dict:
        return await self.c.gameinfo_get(f"/players/{player_id}", ttl=120)

    async def player_kills(self, player_id: str) -> list:
        return await self.c.gameinfo_get(f"/players/{player_id}/kills", ttl=60)

    async def player_deaths(self, player_id: str) -> list:
        return await self.c.gameinfo_get(f"/players/{player_id}/deaths", ttl=60)

    async def player_statistics(
        self, type_: str = "PvE", range_: str = "week", limit: int = 11, **kw
    ) -> Any:
        params = {"type": type_, "range": range_, "limit": limit, **kw}
        return await self.c.gameinfo_get("/players/statistics", params=params, ttl=300)

    # --- 公会 ---
    async def guild(self, guild_id: str) -> dict:
        return await self.c.gameinfo_get(f"/guilds/{guild_id}", ttl=300)

    async def guild_members(self, guild_id: str) -> list:
        return await self.c.gameinfo_get(f"/guilds/{guild_id}/members", ttl=300)

    # --- 击杀 / 死亡事件 ---
    async def events(
        self, guild_id: Optional[str] = None, limit: int = 51, offset: int = 0
    ) -> list:
        params: dict = {"limit": min(limit, 51), "offset": offset}
        if guild_id:
            params["guildId"] = guild_id
        return await self.c.gameinfo_get("/events", params=params, ttl=30)

    async def event(self, event_id: str) -> dict:
        return await self.c.gameinfo_get(f"/events/{event_id}", ttl=300)

    # --- 战役（ZvZ） ---
    async def battles(
        self,
        guild_id: Optional[str] = None,
        range_: str = "week",
        sort: str = "recent",
        limit: int = 20,
        offset: int = 0,
    ) -> list:
        params: dict = {"range": range_, "sort": sort, "limit": limit, "offset": offset}
        if guild_id:
            params["guildId"] = guild_id
        return await self.c.gameinfo_get("/battles", params=params, ttl=120)

    async def battle(self, battle_id: str) -> dict:
        """单场战役详情；`players` 为参与玩家 dict，len 即总参战人数。"""
        return await self.c.gameinfo_get(f"/battles/{battle_id}", ttl=300)

    async def battle_events(self, battle_id: str, limit: int = 51, offset: int = 0) -> list:
        params = {"limit": min(limit, 51), "offset": offset}
        return await self.c.gameinfo_get(
            f"/events/battle/{battle_id}", params=params, ttl=300
        )

    # --- 声望榜 ---
    async def player_fame(self, range_: str = "week", limit: int = 11) -> list:
        return await self.c.gameinfo_get(
            "/events/playerfame", params={"range": range_, "limit": limit}, ttl=300
        )

    async def guild_fame(self, range_: str = "week", limit: int = 11) -> list:
        return await self.c.gameinfo_get(
            "/events/guildfame", params={"range": range_, "limit": limit}, ttl=300
        )
