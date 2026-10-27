"""内置：/help 查看插件与命令，/status 查看运行状态。"""

from __future__ import annotations

import logging

from ..core import EventContext
from fluffs.config import get_active_config

_cfg = get_active_config()
_prefixes = _cfg.bot.command_prefixes if _cfg else []
command_prefix = (_prefixes or ["//"])[0]

logger = logging.getLogger(__name__)

__plugin_meta__ = {
    "name": "help",
    "description": "内置：列出已加载插件与运行状态",
    "usage": f"{command_prefix}help [插件名]、{command_prefix}status",
    "version": "0.2.0",
}


def _format_plugins(bot) -> str:
    lines = ["已加载插件："]
    for meta in bot.plugins.loaded.values():
        usage = f"  用法: {meta.usage}" if meta.usage else ""
        lines.append(f"· {meta.name} — {meta.description or '（无描述）'}{usage}")
    if len(lines) == 1:
        lines.append("（无）")
    return "\n".join(lines)


def setup(bot) -> None:
    @bot.on_command("help", "帮助")
    async def help_cmd(ctx: EventContext) -> None:
        target = ctx.args.strip()
        if target and target in bot.plugins.loaded:
            meta = bot.plugins.loaded[target]
            await ctx.reply(f"{meta.name} v{meta.version}\n{meta.description}\n用法: {meta.usage or '未标注'}")
            return
        await ctx.reply(_format_plugins(bot))

    @bot.on_command("status", "status")
    async def status(ctx: EventContext) -> None:
        info = bot.describe()
        lines = [
            "运行状态",
            f"· NapCat 连接: {'已连接' if info['ready'] else '未连接'}",
            f"· 登录账号: {info['self_id'] or '未知'}",
            f"· 处理函数: {info['handlers']} 个",
            f"· 插件: {', '.join(info['plugins']) or '无'}",
            f"· 连接模式: {bot.config.connection.mode}",
        ]
        lines.extend(_service_lines(bot))
        await ctx.reply("\n".join(lines))


def _service_lines(bot) -> list[str]:
    lines: list[str] = []
    for name, service in sorted(bot.services.items()):
        render = getattr(service, "status_line", None)
        if callable(render):
            lines.append(f"· {name}: {render()}")
            continue
        stats = getattr(service, "stats", None)
        if callable(stats):
            data = stats()
            if isinstance(data, dict):
                pairs = [f"{key}={value}" for key, value in data.items() if not isinstance(value, str) or len(value) <= 24]
                lines.append(f"· {name}: " + ", ".join(pairs))
                continue
        try:
            size = len(service)
        except TypeError:
            lines.append(f"· {name}: {type(service).__name__}")
        else:
            lines.append(f"· {name}: {size} 项")
    return lines
