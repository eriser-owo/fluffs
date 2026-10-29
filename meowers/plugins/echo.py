from __future__ import annotations

from fluffs.config import get_active_config
from fluffs.core import EventContext

_cfg = get_active_config()
_prefixes = _cfg.bot.command_prefixes if _cfg else []
command_prefix = (_prefixes or ["//"])[0]

__plugin_meta__ = {
    "name": "echo",
    "description": f"{command_prefix}echo 复读",
    "usage": f"{command_prefix}echo <内容> 或 {command_prefix}复读 <内容>",
    "version": "0.1.0",
    "author": "eriser-owo",
}


def setup(bot) -> None:
    @bot.on_command("echo", "复读")
    async def echo(ctx: EventContext) -> None:
        if not ctx.args:
            await ctx.reply(f"用法：{command_prefix}echo <内容>")
            return
        await ctx.reply(ctx.args)