"""自动复读：群里 WINDOW 秒内被 THRESHOLD 个不同的人发同一条消息，Bot 就跟着复读一遍。"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from fluffs.config import get_active_config
from fluffs.core import EventContext, rules

logger = logging.getLogger(__name__)

WINDOW = 60.0      # 统计窗口（秒）
THRESHOLD = 3      # 需要多少个「不同的人」
COOLDOWN = 60.0    # 复读之后的冷却（秒），期间同一条消息不再复读
MAX_LEN = 200      # 超过这个长度的消息不参与（别复读大段文本刷屏）

_cfg = get_active_config()
_prefixes = tuple(_cfg.bot.command_prefixes) if _cfg else ()

__plugin_meta__ = {
    "name": "auto_echo",
    "description": f"自动复读：{WINDOW:.0f} 秒内 {THRESHOLD} 个不同的人说同一句话就跟着复读",
    "usage": "无需命令，自动生效；阈值见本文件顶部的常量",
    "version": "0.1.0",
    "author": "Eriser",
}


class AutoEchoState:
    """按群统计「同一条文本被谁说过」。"""

    def __init__(self) -> None:
        # group_id -> {文本: deque[(时间, user_id)]}
        self._recent: dict[int, dict[str, deque[tuple[float, int]]]] = defaultdict(dict)
        # (group_id, 文本) -> 冷却结束时间
        self._cool: dict[tuple[int, str], float] = {}
        self.echoes = 0

    def observe(self, group_id: int, user_id: int, text: str, now: float) -> bool:
        """记一条消息；返回 True 表示这一轮该复读了。"""
        texts = self._recent[group_id]

        # 顺手清掉整组里过期的文本，长跑也不会把字典撑大
        for stale in [key for key, dq in texts.items() if not dq or now - dq[-1][0] > WINDOW]:
            del texts[stale]

        if self._cooling(group_id, text, now):
            return False

        bucket = texts.setdefault(text, deque())
        while bucket and now - bucket[0][0] > WINDOW:
            bucket.popleft()
        bucket.append((now, user_id))

        if len({uid for _ts, uid in bucket}) < THRESHOLD:
            return False

        # 凑够人了：清掉这一条、进冷却，保证一次刷屏只复读一条
        texts.pop(text, None)
        self._cool[(group_id, text)] = now + COOLDOWN
        self._prune_cool(now)
        self.echoes += 1
        return True

    def status_line(self) -> str:
        pending = sum(len(texts) for texts in self._recent.values())
        return f"{self.echoes} 次复读 · 正在追踪 {pending} 条 / {len(self._recent)} 个群"

    def _cooling(self, group_id: int, text: str, now: float) -> bool:
        until = self._cool.get((group_id, text))
        if until is None:
            return False
        if now < until:
            return True
        del self._cool[(group_id, text)]
        return False

    def _prune_cool(self, now: float) -> None:
        if len(self._cool) < 256:
            return
        for key in [k for k, until in self._cool.items() if until <= now]:
            del self._cool[key]



def setup(bot) -> None:
    state = AutoEchoState()
    bot.services["auto_echo"] = state          # /status 直接显示 status_line()

    #群消息：窗口内凑够 THRESHOLD 个不同的人就复读（priority 50 = 命令 10 / LLM 20 之后跑）
    @bot.on_message(rules.group_only, priority=50)
    async def on_group_message(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None:
            return

        text = event.plain_text.strip()
        if not text or len(text) > MAX_LEN:
            return
        if _prefixes and text.startswith(_prefixes):
            return

        self_id = event.self_id or bot.api.self_id or bot.config.bot.self_id
        if self_id and event.user_id == self_id:
            return

        if not state.observe(event.group_id, event.user_id, text, time.monotonic()):
            return

        logger.info("「%.30s」被 %d 个不同的人说了喵，复读一遍~", text, THRESHOLD)
        try:
            await ctx.send(text)  # 原样复读，不 @ 人
        except Exception:
            logger.exception("复读失败喵: %.50s", text)