"""示例插件：定时任务——每天定点在群里发早晚安提醒（演示 bot.scheduler.daily）。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__plugin_meta__ = {
    "name": "reminder",
    "description": "示例：每天 08:00 早安、22:00 晚安（演示 bot.scheduler.daily）",
    "usage": "无需命令，自动生效；时间改本文件 setup() 里的 daily()",
    "version": "0.1.0",
    "author": "eriser-owo",
}


async def _broadcast(bot, text: str) -> None:
    """给 bot 所在的所有群各发一条消息。"""
    try:
        for group in await bot.api.get_group_list():
            gid = int(group.get("group_id", 0))
            if gid:
                await bot.api.send_group_msg(gid, text)
    except Exception:
        logger.exception("定时播报失败喵")


async def setup(bot) -> None:
    async def morning(bot) -> None:
        await _broadcast(bot, "早安喵~")

    async def night(bot) -> None:
        await _broadcast(bot, "晚安喵，早点睡~")

    # 每天定点（也可写成 bot.scheduler.daily(8, 0, morning)）
    bot.scheduler.daily("08:00", morning, name="morning-reminder")
    bot.scheduler.daily("22:00", night, name="night-reminder")

    # 周期任务示例：每小时跑一次
    # async def hourly(bot) -> None:
    #     await _broadcast(bot, "整点报时喵~")
    # bot.scheduler.every(3600, hourly, name="hourly")

    logger.info("定时提醒装好啦喵 08:00 早安 / 22:00 晚安")
