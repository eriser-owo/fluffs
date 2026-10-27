"""LLM 提供者抽象与注册表。

与 QQ / OneBot 无关：只负责"把一串消息发给模型、拿回文本"。
接入新服务：实现 ``ChatProvider`` 子类 + ``@register_provider``。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from ....config import LLMConfig

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ChatMessage:
    """一条对话消息。"""

    role: str  # system | user | assistant
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


class LLMError(Exception):
    """LLM 调用失败。"""


class LLMNotConfigured(LLMError):
    """未配置可用的提供者（没开 enabled 或没填 api_key）。"""


class ChatProvider(ABC):
    """对话模型提供者接口。"""

    name: ClassVar[str] = "base"

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    @property
    def available(self) -> bool:
        return bool(self.config.api_key)

    @abstractmethod
    async def complete(self, messages: Sequence[ChatMessage], **overrides: Any) -> str:
        """一次性返回完整回复文本。overrides 可覆盖 model / temperature / max_tokens。"""

    def stream(self, messages: Sequence[ChatMessage], **overrides: Any) -> AsyncIterator[str]:
        """预留：流式输出。默认不支持，需要时在子类里实现。"""
        raise NotImplementedError(f"{self.name} 暂不支持流式输出")

    async def aclose(self) -> None:
        """释放底层资源（HTTP 连接池等）。"""


# --- 注册表 ---------------------------------------------------------------
_PROVIDERS: dict[str, type[ChatProvider]] = {}


def register_provider(cls: type[ChatProvider]) -> type[ChatProvider]:
    """类装饰器：注册一个提供者实现。"""
    if not getattr(cls, "name", None) or cls.name == "base":
        raise ValueError(f"{cls.__name__} 必须定义唯一的 name")
    _PROVIDERS[cls.name] = cls
    return cls


def available_providers() -> list[str]:
    return sorted(_PROVIDERS)


def create_provider(config: LLMConfig) -> ChatProvider | None:
    """按配置创建提供者；不可用时返回 None 并给出原因日志。"""
    if not config.enabled:
        logger.info("LLM 还没开火喵（llm.enabled=false），对话模块只负责打招呼~")
        return None
    cls = _PROVIDERS.get(config.provider)
    if cls is None:
        logger.error("这个 LLM provider 我不认识喵 %r，可选: %s", config.provider, ", ".join(available_providers()))
        return None
    provider = cls(config)
    if not provider.available:
        logger.warning("LLM provider %s 还缺把钥匙喵，去 config.toml 或 .env 补个 api_key 吧~", config.provider)
        return None
    logger.info("LLM provider 就位啦喵 %s（model=%s）", config.provider, config.model)
    return provider
