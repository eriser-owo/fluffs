"""插件：群友回复机器人的某条消息并说「撤回」，机器人就撤回那条消息。

不是机器人自己的消息 / 查不到 / 超过可撤回时间，都静默不动。
"""

from __future__ import annotations

import logging

from fluffs.core import EventContext, rules

logger = logging.getLogger(__name__)

__plugin_meta__ = {
    "name": "recall",
    "description": "回复机器人的消息并说「撤回」，机器人会撤回那条消息",
    "usage": "回复机器人某条消息 + 撤回",
    "version": "0.1.0",
    "author": "eriser-owo",
}


def setup(bot) -> None:
    @bot.on_message(
        rules.all_of(
            rules.group_only,
            rules.regex(r"^\s*撤回\s*$"),
        ),
        priority=10,
    )
    async def on_recall(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None:
            return

        # 拿到被引用的消息 id
        reply_segs = event.get_segments("reply")
        if not reply_segs:
            return
        raw_id = reply_segs[0].get("data", {}).get("id")
        try:
            quoted_id = int(raw_id)
        except (TypeError, ValueError):
            return

        # 只撤回机器人自己的消息（避免误删群友的）
        try:
            info = await bot.api.get_msg(quoted_id)
        except Exception:
            return  # 查不到就不动
        sender = info.get("sender") or {}
        if int(sender.get("user_id") or 0) != bot.api.self_id:
            return  # 不是机器人的消息，不动

        try:
            await bot.api.delete_msg(quoted_id)
            logger.info("撤回了一条消息喵 message_id=%s", quoted_id)
        except Exception:
            logger.debug("这条撤回不了喵 message_id=%s", quoted_id)
