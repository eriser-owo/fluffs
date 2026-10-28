"""示例插件：处理通知事件（群里被戳一戳就回应）。
"""

from __future__ import annotations

from fluffs.core import EventContext
from fluffs.napcat import NoticeEvent

__plugin_meta__ = {
    "name": "poke",
    "description": "戳一戳时回应",
    "usage": "戳一戳机器人",
    "version": "0.1.0",
    "author": "eriser-owo",
}


def _is_poke(ctx: EventContext) -> bool:
    """戳一戳通知：NapCat 上报为 notify/poke，部分实现用 group_poke，两种都认。"""
    event = ctx.event
    if not isinstance(event, NoticeEvent):
        return False
    return event.notice_type == "group_poke" or (event.notice_type == "notify" and event.sub_type == "poke")


def setup(bot) -> None:
    @bot.on_notice(_is_poke)
    async def on_poke(ctx: EventContext) -> None:
        event = ctx.event
        if not isinstance(event, NoticeEvent):
            return
        # 只回应"戳自己"的，戳别人不插嘴；self_id 优先取事件自带的
        self_id = event.self_id or ctx.bot.api.self_id or ctx.bot.config.bot.self_id
        if self_id and event.target_id != self_id:
            return
        await ctx.bot.api.send_group_msg(event.group_id, "别戳啦 (＃`Д´)")
