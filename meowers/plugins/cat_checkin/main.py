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

from meowers.config import APP_ROOT
from meowers.modules.groups import list_members

logger = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parent / "assets"
DB_PATH = APP_ROOT / "data" / "cat_checkin" / "checkin.db"
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
    """正常签到对勾：checkedin.png，没有就现画一个绿色圆。"""
    p = ASSETS / "checkedin.png"
    if p.is_file():
        return Image.open(p).convert("RGBA").resize((TILE, TILE))
    im = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([TILE * 0.15, TILE * 0.15, TILE * 0.85, TILE * 0.85], fill=(80, 200, 120, 200))
    return im


def _load_makeup():
    """补签标记：makeup.png，没有就现画一个橙色圆（与正常签的绿色区分）。"""
    p = ASSETS / "makeup.png"
    if p.is_file():
        return Image.open(p).convert("RGBA").resize((TILE, TILE))
    im = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([TILE * 0.15, TILE * 0.15, TILE * 0.85, TILE * 0.85], fill=(250, 170, 40, 200))
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


def render_calendar(year, month, grid, normal_total, makeup_total) -> bytes:
    """把签到表画成 PNG，返回字节。

    grid：7 列。格子取值：
        -1          空白（本月没有这天）
        0           未签到
        (count,kind) 已签到：kind='normal' 正常签 / 'makeup' 补签
    """
    first_weekday, days_in_month = calendar.monthrange(year, month)  # 周一=0
    rows = len(grid)

    width = 2 * MARGIN + 7 * TILE + 6 * GAP
    height = HEADER_H + WEEK_H + rows * TILE + (rows - 1) * GAP + 2 * MARGIN
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    draw.text((MARGIN, 8), f"签到 {normal_total} · 补签 {makeup_total}", fill=(40, 40, 40), font=_font(26))
    for col, label in enumerate(("一", "二", "三", "四", "五", "六", "日")):
        cx = MARGIN + col * (TILE + GAP) + TILE // 2
        draw.text((cx, HEADER_H - 2), label, fill=(30, 30, 30), font=_font(18), anchor="ma")

    checked = _load_checked()
    makeup_overlay = _load_makeup()
    for r in range(rows):
        for c in range(7):
            day = r * 7 + c - first_weekday + 1
            if not (1 <= day <= days_in_month):
                continue  # 本月没有这一天
            cell = grid[r][c]
            x = MARGIN + c * (TILE + GAP)
            y = HEADER_H + WEEK_H + r * (TILE + GAP)

            img.paste(_load_tile(year, month, day), (x, y))       # 中间：自定义图

            if isinstance(cell, tuple):
                count, kind = cell
                if kind == "makeup":
                    img.paste(makeup_overlay, (x, y - 6), makeup_overlay)   # 补签：橙色 + 补字
                    draw.text((x + 4, y + 4), "补", fill="white", font=_font(18), anchor="la",
                              stroke_width=2, stroke_fill=(170, 110, 20))
                else:
                    img.paste(checked, (x, y - 6), checked)                  # 正常签：绿色对勾
                    if count >= 2:
                        draw.text((x + TILE - 4, y + TILE - 5), f"x{count}",
                                  fill="white", font=_font(24), anchor="rs",
                                  stroke_width=2, stroke_fill=(90, 90, 90))

            draw.text((x + 4, y + TILE - 5), f"{day:02d}",                # 左下角日期
                      fill="white", font=_font(15), anchor="ls",
                      stroke_width=2, stroke_fill=(90, 90, 90))

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _fit_text(draw, text, font, max_width):
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…"


def render_board(rows) -> bytes:
    """画月榜"""
    W = 500
    HEADER_H = 64
    ROW_H = 44
    PAD = 20          # 四周纯色缓冲区
    n = len(rows)
    body_h = n * ROW_H

    img = Image.new("RGB", (W + 2 * PAD, 2 * PAD + HEADER_H + body_h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 蓝色表头
    header_top = PAD
    draw.rectangle([PAD, header_top, PAD + W, header_top + HEADER_H], fill=(70, 130, 246))
    title_font = _font(26)
    title = "本月签到榜"
    title_w = draw.textlength(title, font=title_font)
    draw.text(
        (PAD + (W - title_w) // 2, header_top + (HEADER_H - 26) // 2),
        title, font=title_font, fill="white",
    )

    # 灰色表格体
    body_top = header_top + HEADER_H
    draw.rectangle([PAD, body_top, PAD + W, body_top + body_h], fill=(238, 240, 245))

    name_font = _font(20)
    rank_font = _font(20)
    count_font = _font(20)

    for i, (rank, name, count) in enumerate(rows):
        row_y = body_top + i * ROW_H
        cy = row_y + ROW_H // 2

        # 排名
        draw.text((PAD + 26, cy - 10), str(rank), font=rank_font, fill=(40, 40, 40))

        name = _fit_text(draw, name, name_font, 280)
        draw.text((PAD + 72, cy - 10), name, font=name_font, fill=(30, 30, 30))

        cnt = f"{count}发"
        cnt_w = draw.textlength(cnt, font=count_font)
        draw.text((PAD + W - 20 - cnt_w, cy - 10), cnt, font=count_font, fill=(90, 90, 90))

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
        # 幂等迁移：补签功能加的 kind 列
        cur = await self._db.execute("PRAGMA table_info(checkin)")
        cols = {row[1] for row in await cur.fetchall()}
        await cur.close()
        if "kind" not in cols:
            await self._db.execute(
                "ALTER TABLE checkin ADD COLUMN kind TEXT NOT NULL DEFAULT 'normal'"
            )
        await self._db.commit()

    async def close(self):
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def checkin(self, user_id, *, year=None, month=None, day=None, kind="normal") -> int:
        """记一次签到。默认今天、正常签；补签时显式传 year/month/day/kind='makeup'。"""
        today = date.today()
        y = today.year if year is None else year
        m = today.month if month is None else month
        d = today.day if day is None else day
        await self._db.execute(
            "INSERT INTO checkin(user_id, year, month, day, count, kind) VALUES(?,?,?,?,1,?) "
            "ON CONFLICT(user_id, year, month, day) DO UPDATE SET count = count + 1",
            (user_id, y, m, d, kind),
        )
        await self._db.commit()
        cur = await self._db.execute(
            "SELECT count FROM checkin WHERE user_id=? AND year=? AND month=? AND day=?",
            (user_id, y, m, d),
        )
        row = await cur.fetchone()
        await cur.close()
        self._lifetime += 1
        return int(row[0])

    async def day_state(self, user_id, y, m, d):
        """某天状态：None 表示没签，否则返回 (count, kind)。"""
        cur = await self._db.execute(
            "SELECT count, kind FROM checkin WHERE user_id=? AND year=? AND month=? AND day=?",
            (user_id, y, m, d),
        )
        row = await cur.fetchone()
        await cur.close()
        return (int(row[0]), str(row[1])) if row else None

    async def month_grid(self, user_id, y, m) -> list:
        """返回本月网格：-1 空白 / 0 未签 / (count, kind) 已签。"""
        grid = init_month_table(y, m)
        first_col, days = calendar.monthrange(y, m)
        cur = await self._db.execute(
            "SELECT day, count, kind FROM checkin WHERE user_id=? AND year=? AND month=?",
            (user_id, y, m),
        )
        states = {day: (cnt, kind) for day, cnt, kind in await cur.fetchall()}
        await cur.close()
        for d in range(1, days + 1):
            r, c = divmod(first_col + d - 1, 7)
            if d in states:
                grid[r][c] = states[d]
        return grid

    async def month_total(self, user_id, y, m, kind=None) -> int:
        """本月累计次数；kind 给 'normal'/'makeup' 只算某类，None 算全部。"""
        sql = "SELECT COALESCE(SUM(count), 0) FROM checkin WHERE user_id=? AND year=? AND month=?"
        params = [user_id, y, m]
        if kind is not None:
            sql += " AND kind=?"
            params.append(kind)
        cur = await self._db.execute(sql, params)
        row = await cur.fetchone()
        await cur.close()
        return int(row[0])

    async def month_board(self, y, m, user_ids) -> dict:
        """给定一批 user_id，返回 {user_id: 本月签到总次数}（只含有签到的）。"""
        if not user_ids:
            return {}
        placeholders = ",".join("?" * len(user_ids))
        cur = await self._db.execute(
            f"SELECT user_id, SUM(count) FROM checkin "
            f"WHERE year=? AND month=? AND user_id IN ({placeholders}) GROUP BY user_id",
            (y, m, *user_ids),
        )
        rows = await cur.fetchall()
        await cur.close()
        return {int(uid): int(total) for uid, total in rows if total}

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
                rules.regex(r"^\s*草猫\s*$"),
                rules.regex(r"^\s*👒\s*$"),
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
            normal = await state.month_total(event.user_id, today.year, today.month, "normal")
            makeup = await state.month_total(event.user_id, today.year, today.month, "makeup")
            png = render_calendar(today.year, today.month, grid, normal, makeup)
            image = msg.image("base64://" + base64.b64encode(png).decode())
            await ctx.reply(msg.build(f"成功草猫了（今日第 {count} 发）：", image))
        except Exception:
            logger.exception("猫猫签到翻车啦喵")
            await ctx.reply("猫猫签到翻车啦喵，看下日志")

    @bot.on_command("补草", prefixes=[""])
    async def on_makeup(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None or not event.is_group:
            await ctx.reply("这个命令要在群里用喵")
            return

        arg = ctx.args.strip()
        if not arg.isdigit():
            await ctx.reply("用法：补签 {几号}，比如「补签 15」")
            return

        dd = int(arg)
        today = date.today()
        days_in_month = calendar.monthrange(today.year, today.month)[1]

        if not (1 <= dd <= days_in_month):
            await ctx.reply(f"哈哈，好笨。本月没有 {dd} 号喵")
            return
        if dd >= today.day:
            await ctx.reply("只能补过去的喵")
            return

        try:
            if await state.day_state(event.user_id, today.year, today.month, dd) is not None:
                await ctx.reply(f"{dd} 号已经草过猫了喵，不用补")
                return

            await state.checkin(
                event.user_id, year=today.year, month=today.month, day=dd, kind="makeup"
            )
            grid = await state.month_grid(event.user_id, today.year, today.month)
            normal = await state.month_total(event.user_id, today.year, today.month, "normal")
            makeup = await state.month_total(event.user_id, today.year, today.month, "makeup")
            png = render_calendar(today.year, today.month, grid, normal, makeup)
            image = msg.image("base64://" + base64.b64encode(png).decode())
            await ctx.reply(msg.build(f"补签成功喵，{dd} 号已补上：", image))
        except Exception:
            logger.exception("补签翻车啦喵")
            await ctx.reply("补签翻车啦喵，看下日志")

    @bot.on_message(
        rules.all_of(
            rules.group_only,
            rules.regex(r"^\s*签到榜\s*$"),
        ), priority=50)
    async def on_board(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None:
            return
        try:
            today = date.today()
            members = await list_members(event.group_id, "active")
            if not members:
                await ctx.send("名册还没同步喵，稍后再试")
                return
            board = await state.month_board(
                today.year, today.month, [m.user_id for m in members]
            )
            if not board:
                await ctx.send("本月还没有人签到喵")
                return
            name_map = {m.user_id: m.display_name for m in members}
            ranked = sorted(board.items(), key=lambda kv: kv[1], reverse=True)
            rows = [
                (i, name_map.get(uid, str(uid)), total)
                for i, (uid, total) in enumerate(ranked, 1)
            ]
            png = render_board(rows)
            image = msg.image("base64://" + base64.b64encode(png).decode())
            await ctx.send(msg.build("本月签到榜", image))
        except Exception:
            logger.exception("榜单翻车啦喵")
            await ctx.send("榜单翻车啦喵，看下日志")

    async def teardown(_bot) -> None:
        bot.services.pop("cat_checkin", None)
        await state.close()

    bot.on_teardown(teardown)
