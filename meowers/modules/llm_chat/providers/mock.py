"""调试用假模型：不联网、不校验 api_key，把收到的输入原样回显。

用途：在没有 API Key、或想单独验证「@触发 → 输入组装 → 回复」链路时使用。

    $env:FLUFFS_LLM_ENABLED="true"; $env:FLUFFS_LLM_PROVIDER="mock"; python main.py
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .base import ChatMessage, ChatProvider, register_provider


@register_provider
class MockProvider(ChatProvider):
    name = "mock"

    def __init__(self, config) -> None:
        super().__init__(config)
        self.last_messages: list[ChatMessage] = []

    @property
    def available(self) -> bool:
        return True  # 不需要 api_key

    async def complete(self, messages: Sequence[ChatMessage], **overrides: Any) -> str:
        self.last_messages = list(messages)
        user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return f"【mock】收到的输入：\n{user}"
