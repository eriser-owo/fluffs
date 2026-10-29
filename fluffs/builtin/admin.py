"""admin 插件：提供内置的管理命令，如测活和热重载。"""
from __future__ import annotations

import platform
import sys
from ..core import EventContext, rules
from fluffs.config import get_active_config


_cfg = get_active_config()
_prefixes = _cfg.bot.command_prefixes if _cfg else []
command_prefix = (_prefixes or ["//"])[0]


__plugin_meta__ = {
    "name": "admin",
    "description": f"内置：{command_prefix}ping 测活、{command_prefix}reload 热重载插件（仅超级用户）、{command_prefix}napcat 一些NapCat版本提示",
    "usage": f"无",
    "version": "0.2.0",
}


def setup(bot) -> None:

    @bot.on_command("ping", rule=rules.from_superuser())
    async def ping(ctx: EventContext) -> None:

        await ctx.reply("pong")

    @bot.on_command("reload", rule=rules.from_superuser())
    async def reload_plugin(ctx: EventContext) -> None:

        name = ctx.args.strip()

        if not name:
            available = ", ".join(bot.plugins.loaded.keys())
            await ctx.reply(f"用法：{command_prefix}reload <插件名>\n可重载: {available or '无'}")
            return


        meta = await bot.plugins.reload(name)
        if meta is None:
            await ctx.reply(f"插件 {name} 未找到或重载失败，请看控制台日志")
            return

        await ctx.reply(f"插件 {meta.name} 已重载，共 {len(bot.dispatcher.handlers)} 个处理函数")

    @bot.on_command("napcat")
    async def napcat(ctx: EventContext) -> None:
        version_data = {}
        try:
            version_data = await bot.api.get_version_info()  # Transport.call 已返回 data
        except Exception:
            pass  # 版本获取失败时不阻断，继续展示环境信息
        lines = ["NapCat 运行环境"]
        if version_data:
            lines.append(f"应用: {version_data.get('app_name', '未知')}")
            lines.append(f"协议: {version_data.get('protocol_version', '未知')}")
            lines.append(f"版本: {version_data.get('app_version', '未知')}")
        else:
            lines.append("OneBot 版本信息: 获取失败")
        lines.append(f"系统: {platform.system()} {platform.release()}")
        lines.append(f"架构: {platform.machine()}")
        lines.append(f"Python: {sys.version.split()[0]}")

        await ctx.reply("\n".join(lines))