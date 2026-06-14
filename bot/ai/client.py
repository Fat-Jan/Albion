"""OpenAI 兼容 AI 客户端。LongCat base_url 用 https://api.longcat.chat/openai。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import httpx

from bot import config


class AIClientError(RuntimeError):
    """AI 服务不可用或响应格式不符合预期。"""


@dataclass(frozen=True)
class AIClientConfig:
    base_url: str
    api_key: str
    model: str
    timeout: float = 20.0
    max_output_tokens: int = 800

    @classmethod
    def from_env(cls) -> "AIClientConfig":
        return cls(
            base_url=config.AI_BASE_URL,
            api_key=config.AI_API_KEY,
            model=config.AI_MODEL,
            timeout=config.AI_TIMEOUT_SEC,
            max_output_tokens=config.AI_MAX_OUTPUT_TOKENS,
        )


class AIClient:
    def __init__(
        self,
        cfg: AIClientConfig,
        *,
        transport: Callable[[httpx.Request], httpx.Response] | None = None,
    ) -> None:
        self.cfg = cfg
        kwargs: dict[str, Any] = {
            "timeout": cfg.timeout,
            "headers": {
                "Authorization": f"Bearer {cfg.api_key}",
                "Content-Type": "application/json",
            },
        }
        if transport:
            kwargs["transport"] = httpx.MockTransport(transport)
        self._client = httpx.AsyncClient(**kwargs)

    @property
    def chat_completions_url(self) -> str:
        base = self.cfg.base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    async def complete(
        self, messages: list[dict[str, str]], *, max_tokens: int | None = None
    ) -> str:
        payload = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens or self.cfg.max_output_tokens,
        }
        try:
            resp = await self._client.post(self.chat_completions_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AIClientError("AI 请求失败") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIClientError("AI 响应格式异常") from exc
        return str(content).strip()

    async def aclose(self) -> None:
        await self._client.aclose()
