"""这只是一个示例插件，用来演示如何发送语音
如果你没有文件data/etc/test.wav，这个不可用
"""

from __future__ import annotations

import logging

from fluffs.config import get_active_config
from fluffs.core import EventContext
from fluffs.napcat import message as msg

from meowers.config import APP_ROOT

logger = logging.getLogger(__name__)

_cfg = get_active_config()
_prefixes = _cfg.bot.command_prefixes if _cfg else []
command_prefix = (_prefixes or ["//"])[0]

VOICE_FILE = APP_ROOT / "data" / "etc" / "test.wav"

__plugin_meta__ = {
    "name": "voice_test",
    "description": f"示例",
    "usage": f"{command_prefix}voicetest",
    "version": "0.1.0",
    "author": "eriser-owo",
}


def setup(bot) -> None:
    @bot.on_command("voice")
    async def voicetest(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None or not event.is_group:
            await ctx.reply("这个命令要在群里用喵")
            return

        if not VOICE_FILE.is_file():
            logger.error("语音文件找不到喵: %s", VOICE_FILE)
            await ctx.reply(f"语音文件不存在：{VOICE_FILE}")
            return

        try:
            await ctx.send(msg.record(str(VOICE_FILE)))
        except Exception:
            logger.exception("发语音失败喵: %s", VOICE_FILE)
            await ctx.reply("发语音翻车啦喵，看下日志")
