"""LLM 对话模块。

组成（都在这个目录里）：
    prompt.py            输入组装：昵称 / 职位 / 原文
    module.py            触发与回复：仅被 @ 时触发，单条输入
    providers/           模型提供者：抽象 + 注册表 + OpenAI 兼容实现 + mock

触发规则：群聊必须 @ 机器人；私聊是否响应由 ``config.llm.allow_private`` 决定（默认否）。
每次只把这一条 @ 消息交给模型，不做多轮上下文；聊天记录由 modules/chatlog 负责。
"""

from __future__ import annotations

from .module import setup
from .prompt import build_user_input

__all__ = ["build_user_input", "setup"]
