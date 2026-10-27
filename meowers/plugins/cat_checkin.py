from __future__ import annotations

from fluffs import FluffsBot
from fluffs.config import get_active_config
from fluffs.core import EventContext, rules
from fluffs.napcat import message as msg
import calendar
from datetime import date
import aiosqlite
import base64
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

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

ASSETS = Path(__file__).resolve().parent / "assets" / "cat_checkin"

TILE = 128        # 格子边长(px)
MARGIN = 4        # 最左/最右列 tile 与图片边缘的间距
GAP = 2           # tile 之间间隔；0 = 紧贴（不画线，只是留缝）
HEADER_H = 40     # “本月checkin了 X 次”这一行
WEEK_H = 24       # “1 2 3 4 5 6 日”这一行
BG = (245, 245, 245)

FONT_CANDIDATES = (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)



def init_month_table(year=None, month=None):
    """初始化一个 n 行 x 7 列的表格(嵌套 list)，列顺序为 周一..周日。
    本月有日期的位置填 0，空白位置填 -1。
    year/month 不传时取当前月。
    """
    today = date.today()
    year = today.year if year is None else year
    month = today.month if month is None else month

    first_col = calendar.monthrange(year, month)[0]
    days = calendar.monthrange(year, month)[1]

    n = (first_col + days + 6) // 7
    table = [[-1] * 7 for _ in range(n)]
    for d in range(1, days + 1):
        r, c = divmod(first_col + d - 1, 7)
        table[r][c] = 0
    return table

def render_calendar(year, month, grid, month_total) -> bytes:
    pass

def _load_tile(year, month, day) -> Image.Image:
    pass

def _load_checked() -> Image.Image:
    pass

def _font(size):
    pass

class CatCheckinState:
    def __init__(self, db_path):
        self._db = None
    async def open(self):
        pass
    async def close(self):
        pass
    async def checkin(self, user_id) -> int:
        pass
    async def month_grid(self, user_id, y, m) -> list:
        pass
    async def month_total(self, user_id, y, m) -> int:
        pass
    def status_line(self) -> str:
        pass

def setup(bot) -> None:
    @bot.on_message(rules.all_of(rules.group_only, rules.regex(r"^草猫$")), priority=50)
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
