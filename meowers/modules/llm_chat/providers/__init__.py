"""LLM 提供者：抽象 + 注册表 + 内置实现。

接入新的模型服务：实现 ``ChatProvider`` 子类并用 ``@register_provider`` 注册，
然后在 ``config.toml`` 把 ``llm.provider`` 改成该类的 ``name``。
内置 ``openai_compat``（OpenAI/DeepSeek/通义/Ollama 等 /v1 接口）与 ``mock``（本地假模型，便于调试）。
"""

from __future__ import annotations

from .base import (
    ChatMessage,
    ChatProvider,
    LLMError,
    LLMNotConfigured,
    available_providers,
    create_provider,
    register_provider,
)

# 导入内置实现以触发注册
from .mock import MockProvider  # noqa: F401  (side effect)
from .openai_compat import OpenAICompatProvider  # noqa: F401  (side effect)

__all__ = [
    "ChatMessage",
    "ChatProvider",
    "LLMError",
    "LLMNotConfigured",
    "MockProvider",
    "OpenAICompatProvider",
    "available_providers",
    "create_provider",
    "register_provider",
]
