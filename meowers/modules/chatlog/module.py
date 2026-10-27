"""聊天记录模块的装配：把群消息喂给 recorder，并把实例放到 ``bot.services["chatlog"]``。

记录范围由 ``config.chatlog.scope`` 决定：
    all      记录所有群消息
    mention  只记录 @ 了机器人的消息
只记群聊；要连私聊一起存档，把 ``rules.group_only`` 去掉即可。
"""

from __future__ import annotations

import logging

from fluffs.core import EventContext, rules
from .recorder import ChatLogRecorder

logger = logging.getLogger(__name__)

__plugin_meta__ = {
    "name": "chatlog",
    "description": "聊天记录归档：内存缓冲 + 定时落盘（data/chatlog/*.jsonl）",
    "usage": "无需命令，配置见 config.toml 的 [chatlog]",
    "version": "0.2.0",
}


async def setup(bot) -> None:
    config = bot.config.chatlog
    if not config.enabled:
        logger.info("聊天记录归档被关掉了喵，这次就不记啦~")
        return None

    recorder = ChatLogRecorder(config)
    await recorder.start()
    bot.services["chatlog"] = recorder

    only_mentions = config.scope == "mention"
    mentioned = rules.to_me()

    # priority 调大：先让其它插件处理完，再顺手记录（block=False 不影响别人）
    @bot.on_message(rules.group_only, priority=90)
    async def record_group_message(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None or not event.plain_text.strip():
            return
        if only_mentions and not mentioned(ctx):
            return
        await recorder.record(event)

    async def teardown(_bot) -> None:
        bot.services.pop("chatlog", None)
        await recorder.aclose()

    bot.on_teardown(teardown)
