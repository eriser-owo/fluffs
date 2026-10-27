"""
    bot.py          装配、生命周期
    dispatcher.py   处理函数注册表与分发
    context.py      上下文
    rules.py        通用规则原语
    loader.py       插件
    from fluffs.core import EventContext, rules
"""

from __future__ import annotations

from .bot import FluffsBot
from .context import EventContext
from .dispatcher import Dispatcher, Handler, HandlerFunc
from .loader import PluginManager, PluginMeta, current_plugin
from .rules import Rule

__all__ = [
    "Dispatcher",
    "EventContext",
    "Handler",
    "HandlerFunc",
    "FluffsBot",
    "PluginManager",
    "PluginMeta",
    "Rule",
    "current_plugin",
]
