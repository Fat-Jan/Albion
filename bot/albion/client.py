"""Albion 数据访问客户端：httpx 异步 + 内存 TTL 缓存 + AODP 限流 + 退避重试。

官方 gameinfo 与 AODP 均无鉴权。AODP 限流 180/分，这里保守取 150/分。
官方 API 偶发故障是社区常态，所有调用走重试 + 退避，失败抛给上层友好降级。
"""
import asyncio
import logging
import time
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from bot import config

log = logging.getLogger(__name__)

USER_AGENT = "albion-kook-bot/0.1 (guild query bot)"


class TTLCache:
    """极简内存缓存，按 key 存 (过期时刻, 值)。单进程 asyncio 单线程，无需加锁。"""

    def __init__(self) -> None:
        self._d: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._d.get(key)
        if item is None:
            return None
        expire, val = item
        if expire < time.monotonic():
            self._d.pop(key, None)
            return None
        return val

    def set(self, key: str, val: Any, ttl: float) -> None:
        self._d[key] = (time.monotonic() + ttl, val)


class RateLimiter:
    """滑动窗口限流：period 秒内最多 max_calls 次。"""

    def __init__(self, max_calls: int, period: float) -> None:
        self.max_calls = max_calls
        self.period = period
        self._calls: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._calls = [t for t in self._calls if t > now - self.period]
            if len(self._calls) >= self.max_calls:
                wait = self._calls[0] + self.period - now
                if wait > 0:
                    await asyncio.sleep(wait)
                now = time.monotonic()
                self._calls = [t for t in self._calls if t > now - self.period]
            self._calls.append(now)


class AlbionClient:
    def __init__(
        self,
        gameinfo_base: str = config.GAMEINFO_BASE,
        aodp_base: str = config.AODP_BASE,
        albionbb_base: str = config.ALBIONBB_BASE,
        timeout: float = 15.0,
    ) -> None:
        self.gameinfo_base = gameinfo_base.rstrip("/")
        self.aodp_base = aodp_base.rstrip("/")
        self.albionbb_base = albionbb_base.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=timeout, headers={"User-Agent": USER_AGENT}
        )
        self._cache = TTLCache()
        self._aodp_limiter = RateLimiter(max_calls=150, period=60.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AlbionClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def _get_json(
        self,
        url: str,
        *,
        params: Optional[dict] = None,
        cache_ttl: float = 0,
        limiter: Optional[RateLimiter] = None,
        retries: int = 3,
    ) -> Any:
        key = url + "?" + urlencode(sorted((params or {}).items()))
        if cache_ttl:
            cached = self._cache.get(key)
            if cached is not None:
                return cached

        backoff = 1.0
        last_exc: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            if limiter:
                await limiter.acquire()
            try:
                resp = await self._client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                if cache_ttl:
                    self._cache.set(key, data, cache_ttl)
                return data
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
                log.warning(
                    "请求失败(%d/%d) %s: %s", attempt, retries, url, exc
                )
                if attempt < retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2
        raise AlbionAPIError(f"请求最终失败: {url}") from last_exc

    async def gameinfo_get(
        self, path: str, params: Optional[dict] = None, ttl: float = 60
    ) -> Any:
        return await self._get_json(
            self.gameinfo_base + path, params=params, cache_ttl=ttl
        )

    async def aodp_get(
        self, path: str, params: Optional[dict] = None, ttl: float = 300
    ) -> Any:
        return await self._get_json(
            self.aodp_base + path,
            params=params,
            cache_ttl=ttl,
            limiter=self._aodp_limiter,
        )

    async def albionbb_get(
        self, path: str, params: Optional[dict] = None, ttl: float = 300
    ) -> Any:
        return await self._get_json(
            self.albionbb_base + path, params=params, cache_ttl=ttl
        )


class AlbionAPIError(RuntimeError):
    """对外 API 重试耗尽后的统一错误，上层捕获给友好提示。"""
