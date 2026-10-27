"""聊天记录归档模块。

    recorder.py   缓冲 + 批量落盘（不依赖 QQ，纯存储逻辑）
    query.py      chatlog.db 只读查询（供其它模块复用）
    module.py     装配：把群消息喂给 recorder，并把实例挂到 bot.services

记录字段：时间、群号、QQ 号、用户名（群名片优先）、职位（群主/管理员/成员）、消息原文。
内存里只留最近若干条，其余定时落盘后释放，长时间运行不会涨内存。
"""

from __future__ import annotations

from .module import setup
from .query import count_messages, query_messages, resolve_db_path
from .recorder import ChatLogRecorder, ChatRecord

__all__ = [
    "ChatLogRecorder",
    "ChatRecord",
    "count_messages",
    "query_messages",
    "resolve_db_path",
    "setup",
]
