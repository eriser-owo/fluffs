"""Fluffs —— 轻量 QQ 机器人框架（OneBot 11 / NapCat）。

框架侧（本包）只提供通用能力，不认识任何业务：

    fluffs.napcat     协议层：WebSocket 传输、事件模型、消息段、API 封装、异常
    fluffs.core       内核：FluffsBot 装配、事件分发、上下文、通用规则、插件加载
    fluffs.builtin    内置管理命令：/help、/status、/ping、/reload
    fluffs.config     框架配置段（connection / bot / log）与通用加载原语
    fluffs.logging_setup  日志初始化

业务功能由 App 以"模块 + 插件"的形式挂上来（本仓库里的 App 是 meowers）。
依赖方向单向：App → Fluffs，框架不 import App 的任何东西。

最小用法：

    from fluffs import FluffsBot
    from fluffs.config import FluffsConfig

    bot = FluffsBot(FluffsConfig())
    asyncio.run(bot.run())
"""

from __future__ import annotations

from .config import BotConfig, ConnectionConfig, FluffsConfig, LogConfig
from .core import Dispatcher, EventContext, FluffsBot, PluginManager, PluginMeta, Rule

__version__ = "0.1.0"

__all__ = [
    "BotConfig",
    "ConnectionConfig",
    "Dispatcher",
    "EventContext",
    "FluffsBot",
    "FluffsConfig",
    "LogConfig",
    "PluginManager",
    "PluginMeta",
    "Rule",
    "__version__",
]
