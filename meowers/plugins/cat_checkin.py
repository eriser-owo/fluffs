from __future__ import annotations

from fluffs import FluffsBot
from fluffs.config import get_active_config
from fluffs.core import EventContext, rules
from fluffs.napcat import message as msg
from PIL import Image
from pathlib import Path
import calendar
from datetime import date
import aiosqlite

_cfg = get_active_config()
_prefixes = _cfg.bot.command_prefixes if _cfg else []
command_prefix = (_prefixes or ["//"])[0]

__plugin_meta__ = {
    "name": "cat_checkin",
    "description": "猫猫签到",
    "usage": f"发送“草猫”即可签到",
    "version": "0.1.0",
    "author": "eriser-owo",
}

class CatCheckinState:
    def __init__(self, bot: FluffsBot):
        self.bot = bot

    @staticmethod
    def init_month_table(year=None, month=None):
        """用于初始化一个 n 行 x 7 列的表格(嵌套 list),列顺序为 周一..周日。
        本月有日期的位置初始化填 0,空白位置填 -1。
        year/month 不传时取当前月。
        预期是：用户本月初次调用草猫指令时，为用户生成此表并存储到./data/cat_checkin内。
        内部目录格式：
        YYYY/MM/Users/xxx.jsonl

        """
        today = date.today()
        year = today.year if year is None else year
        month = today.month if month is None else month

        first_col = calendar.monthrange(year, month)[-1]  # 1 号是周几(周一=0)
        days = calendar.monthrange(year, month)[0]  # 本月天数

        n = (first_col + days + 6) // 7  # 所需行数,向上取整
        table = [[0] * 7 for _ in range(n)]

        for d in range(1, days + 1):
            r, c = divmod(first_col + d - 1, 7)  # 第 d 天落在第 r 行第 c 列
            table[r][c] = 1

        return table


def setup(bot) -> None:

    @bot.on_message("草猫")
    async def return_result(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None or not event.is_group:
            return
        await bot.api.send_group_msg(
            event.group_id,
            msg.build(msg.at(event.user_id), " ", "成功草猫了：", msg.image("")),
        )

    async def teardown(_bot) -> None:
         pass
    bot.on_teardown(teardown)
