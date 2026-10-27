"""OpenAI 兼容接口的提供者。

适配 OpenAI / DeepSeek / 通义 / 智谱 / 本地 vLLM、Ollama(openai 兼容模式) 等，
只要 ``base_url`` 指向形如 ``https://host/v1`` 的服务即可。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import httpx

from .base import ChatMessage, ChatProvider, LLMError, register_provider

logger = logging.getLogger(__name__)


@register_provider
class OpenAICompatProvider(ChatProvider):
    name = "openai_compat"

    def __init__(self, config) -> None:
        super().__init__(config)
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.config.timeout,
            )
        return self._client

    async def complete(self, messages: Sequence[ChatMessage], **overrides: Any) -> str:
        payload = {
            "model": overrides.get("model") or self.config.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": overrides.get("temperature", self.config.temperature),
            "max_tokens": overrides.get("max_tokens", self.config.max_tokens),
        }
        try:
            response = await self._get_client().post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"请求模型服务失败: {exc}") from exc

        if response.status_code >= 400:
            raise LLMError(f"模型服务返回 {response.status_code}: {response.text[:300]}")

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"无法解析模型返回: {response.text[:300]}") from exc

        if not isinstance(content, str):
            raise LLMError("模型返回内容为空")
        usage = data.get("usage") or {}
        logger.debug("模型答完啦喵 一共吃掉 %s tokens~", usage.get("total_tokens"))
        return content.strip()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
