"""猫猫签到：回一张本月日历图。"""

from __future__ import annotations

import base64
import calendar
import io
import logging
from datetime import date
from pathlib import Path

import aiosqlite
from PIL import Image, ImageDraw, ImageFont

from fluffs.core import EventContext, rules
from fluffs.napcat import message as msg

logger = logging.getLogger(__name__)

__plugin_meta__ = {
    "name": "cat_checkin",
    "description": "猫猫签到",
    "usage": "发送即可签到",
    "version": "0.3.0",
    "author": "eriser-owo",
}

ASSETS = Path(__file__).resolve().parent / "assets" / "cat_checkin"
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "cat_checkin" / "checkin.db"
TILE = 128
MARGIN = 4
GAP = 2
HEADER_H = 40
WEEK_H = 24
BG = (245, 245, 245)

FONT_CANDIDATES = (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)

def _font(size):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _load_tile(year, month, day):
    """每日瓦片：指定日期 > 按几号 > 默认图。"""
    names = (
        f"calendar_tile_{month:02d}{day:02d}.png",  # 某月某日的图
        f"calendar_tile_{day:02d}.png",              # 某日的图
        "calendar_tile.png",                          # 默认
    )
    for name in names:
        p = ASSETS / name
        if p.is_file():
            return Image.open(p).convert("RGB").resize((TILE, TILE))
    return Image.new("RGB", (TILE, TILE), (200, 200, 200))


def _load_checked():
    p = ASSETS / "checkedin.png"
    if p.is_file():
        return Image.open(p).convert("RGBA").resize((TILE, TILE))
    im = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([TILE * 0.15, TILE * 0.15, TILE * 0.85, TILE * 0.85], fill=(80, 200, 120, 200))
    return im


def init_month_table(year=None, month=None):
    """初始化一个 n 行 x 7 列的表格(嵌套 list)，列顺序为 周一..周日。
    本月有日期的位置填 0，空白位置填 -1。
    year/month 不传时取当前月。
    """
    today = date.today()
    year = today.year if year is None else year
    month = today.month if month is None else month

    first_col = calendar.monthrange(year, month)[0]  # 1 号是周几(周一=0)
    days = calendar.monthrange(year, month)[1]       # 本月天数

    n = (first_col + days + 6) // 7                  # 所需行数，向上取整
    table = [[-1] * 7 for _ in range(n)]             # 先全部空白
    for d in range(1, days + 1):
        r, c = divmod(first_col + d - 1, 7)          # 第 d 天落在第 r 行第 c 列
        table[r][c] = 0                              # 有效日期 = 未签到
    return table


def render_calendar(year, month, grid, month_total) -> bytes:
    """把签到表画成 PNG，返回字节。grid：7 列，-1 空白 / 0 未签 / >=1 次数。"""
    first_weekday, days_in_month = calendar.monthrange(year, month)  # 周一=0
    rows = len(grid)

    width = 2 * MARGIN + 7 * TILE + 6 * GAP
    height = HEADER_H + WEEK_H + rows * TILE + (rows - 1) * GAP + 2 * MARGIN
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    draw.text((MARGIN, 8), f"本月签到了 {month_total} 次", fill=(40, 40, 40), font=_font(26))
    for col, label in enumerate(("一", "二", "三", "四", "五", "六", "日")):
        cx = MARGIN + col * (TILE + GAP) + TILE // 2
        draw.text((cx, HEADER_H - 2), label, fill=(30, 30, 30), font=_font(18), anchor="ma")

    checked = _load_checked()
    for r in range(rows):
        for c in range(7):
            day = r * 7 + c - first_weekday + 1
            if not (1 <= day <= days_in_month):
                continue  # 本月没有这一天
            cnt = grid[r][c]
            x = MARGIN + c * (TILE + GAP)
            y = HEADER_H + WEEK_H + r * (TILE + GAP)

            img.paste(_load_tile(year, month, day), (x, y))       # 中间：自定义图
            if cnt >= 1:
                img.paste(checked, (x, y - 6), checked)               # 中间叠加对勾
            draw.text((x + 4, y + TILE - 5), f"{day:02d}",        # 左下角日期
                      fill="white", font=_font(15), anchor="ls",
                      stroke_width=2, stroke_fill=(90, 90, 90))
            if cnt >= 2:
                draw.text((x + TILE - 4, y + TILE - 5), f"x{cnt}",  # 右下角次数
                          fill="white", font=_font(24), anchor="rs",
                          stroke_width=2, stroke_fill=(90, 90, 90))

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class CatCheckinState:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self._db: aiosqlite.Connection | None = None
        self._lifetime = 0  # 本进程累计签到次数（status_line 用）

    async def open(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS checkin ("
            "user_id INTEGER NOT NULL, year INTEGER NOT NULL, month INTEGER NOT NULL, "
            "day INTEGER NOT NULL, count INTEGER NOT NULL DEFAULT 0, "
            "PRIMARY KEY (user_id, year, month, day))"
        )
        await self._db.commit()

    async def close(self):
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def checkin(self, user_id) -> int:
        today = date.today()
        await self._db.execute(
            "INSERT INTO checkin(user_id, year, month, day, count) VALUES(?,?,?,?,1) "
            "ON CONFLICT(user_id, year, month, day) DO UPDATE SET count = count + 1",
            (user_id, today.year, today.month, today.day),
        )
        await self._db.commit()
        cur = await self._db.execute(
            "SELECT count FROM checkin WHERE user_id=? AND year=? AND month=? AND day=?",
            (user_id, today.year, today.month, today.day),
        )
        row = await cur.fetchone()
        await cur.close()
        self._lifetime += 1
        return int(row[0])

    async def month_grid(self, user_id, y, m) -> list:
        grid = init_month_table(y, m)
        first_col, days = calendar.monthrange(y, m)
        cur = await self._db.execute(
            "SELECT day, count FROM checkin WHERE user_id=? AND year=? AND month=?",
            (user_id, y, m),
        )
        counts = {day: cnt for day, cnt in await cur.fetchall()}
        await cur.close()
        for d in range(1, days + 1):
            r, c = divmod(first_col + d - 1, 7)
            grid[r][c] = counts.get(d, 0)
        return grid

    async def month_total(self, user_id, y, m) -> int:
        cur = await self._db.execute(
            "SELECT COALESCE(SUM(count), 0) FROM checkin WHERE user_id=? AND year=? AND month=?",
            (user_id, y, m),
        )
        row = await cur.fetchone()
        await cur.close()
        return int(row[0])

    def status_line(self) -> str:
        return f"猫猫签到！本进程 {self._lifetime} 次"


async def setup(bot) -> None:
    state = CatCheckinState(DB_PATH)
    await state.open()
    bot.services["cat_checkin"] = state          # /status 直接显示 status_line()

    @bot.on_message(
        rules.all_of(
            rules.group_only,
            rules.any_of(
                rules.regex(r"^\s*签到\s*$"),
            ),
        ), priority=50)
    async def on_checkin(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None:
            return
        try:
            count = await state.checkin(event.user_id)
            today = date.today()
            grid = await state.month_grid(event.user_id, today.year, today.month)
            total = await state.month_total(event.user_id, today.year, today.month)
            png = render_calendar(today.year, today.month, grid, total)
            image = msg.image("base64://" + base64.b64encode(png).decode())
            await ctx.reply(msg.build(f"成功签到了（今日第 {count} 次）：", image))
        except Exception:
            logger.exception("猫猫签到翻车啦喵")
            await ctx.reply("猫猫签到翻车啦喵，看下日志")

    async def teardown(_bot) -> None:
        bot.services.pop("cat_checkin", None)
        await state.close()

    bot.on_teardown(teardown)
