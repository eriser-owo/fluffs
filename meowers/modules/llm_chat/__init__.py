"""LLM 对话模块。

组成（都在这个目录里）：
    prompt.py            输入组装：昵称 / 职位 / 原文
    memory.py            多轮记忆：SQLite 持久化，每群共享，超限自动总结
    module.py            触发与回复：仅被 @ 时触发，带上下文与摘要
    providers/           模型提供者：抽象 + 注册表 + OpenAI 兼容实现 + mock

触发规则：群聊必须 @ 机器人；私聊是否响应由 ``config.llm.allow_private`` 决定（默认否）。
群聊按「每群一份」共享多轮上下文（旧消息由 LLM 总结、原始记录不删），私聊按用户各记各的；
历史存 data/llm_chat/memory.db。
"""

from __future__ import annotations

from .memory import MEMORY_SIZE, SUMMARY_BATCH, ConversationMemory
from .module import setup
from .prompt import build_user_input

__all__ = ["ConversationMemory", "MEMORY_SIZE", "SUMMARY_BATCH", "build_user_input", "setup"]
