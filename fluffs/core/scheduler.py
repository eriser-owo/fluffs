"""定时任务：让插件按「每 N 秒」或「每天 HH:MM」注册要跑的函数。

用法（插件 setup 里）：

    bot.scheduler.every(60, task)          # 每 60 秒跑一次 task(bot)
    bot.scheduler.daily("08:00", task)     # 每天 08:00 跑一次 task(bot)

``task`` 可为同步或异步，签名 ``task(bot) -> None``。
任务按注册时的插件打标，热重载 / 卸载时自动清掉该插件的所有定时任务。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from .loader import current_plugin

if TYPE_CHECKING:
    from .bot import FluffsBot

logger = logging.getLogger(__name__)

TaskFunc = Callable[["FluffsBot"], Any]


@dataclass(slots=True)
class Schedule:
    func: TaskFunc
    interval: float | None = None      # 秒；周期任务
    hour: int | None = None            # 每日任务：几时
    minute: int | None = None          # 每日任务：几分
    plugin: str | None = None
    name: str = ""
    last_run: float = field(default_factory=time.time)


class Scheduler:
    """定时任务调度器：1 秒粒度，任务串行执行。"""

    def __init__(self, bot: "FluffsBot") -> None:
        self.bot = bot
        self._tasks: list[Schedule] = []
        self._tick: asyncio.Task | None = None

    def start(self) -> None:
        if self._tick is None:
            self._tick = asyncio.create_task(self._loop(), name="fluffs-scheduler")
            logger.info("定时任务调度器开跑啦喵")

    async def stop(self) -> None:
        if self._tick is not None:
            self._tick.cancel()
            await asyncio.gather(self._tick, return_exceptions=True)
            self._tick = None

    def every(self, seconds: float, func: TaskFunc, *, name: str = "") -> Schedule:
        """每 ``seconds`` 秒跑一次 ``func(bot)``。"""
        return self._add(func, interval=max(1.0, float(seconds)), name=name)

    def daily(self, hour, minute=None, func: TaskFunc | None = None, *, name: str = "") -> Schedule:
        """每天在 HH:MM 跑一次 ``func(bot)``。

        两种写法：``daily("08:00", func)`` 或 ``daily(8, 0, func)``。
        """
        if func is None:
            func = minute  # type: ignore[assignment]
            hour, minute = self._parse_time(str(hour))
        hour, minute = int(hour), int(minute)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"非法时间: {hour:02d}:{minute:02d}")
        return self._add(func, hour=hour, minute=minute, name=name)

    @staticmethod
    def _parse_time(spec: str) -> tuple[int, int]:
        hh, _, mm = spec.partition(":")
        return int(hh), int(mm)

    def _add(self, func: TaskFunc, *, interval=None, hour=None, minute=None, name: str = "") -> Schedule:
        sched = Schedule(
            func=func,
            interval=interval,
            hour=hour,
            minute=minute,
            plugin=current_plugin(),
            name=name or getattr(func, "__name__", repr(func)),
            # 周期任务：先等一个间隔；每日任务：若刚好到点则立刻跑一次
            last_run=(0.0 if interval is None else time.time()),
        )
        self._tasks.append(sched)
        logger.debug("登记一个定时任务喵 %s（插件=%s）", sched.name, sched.plugin)
        return sched

    def remove(self, sched: Schedule) -> None:
        if sched in self._tasks:
            self._tasks.remove(sched)

    def remove_plugin(self, plugin: str) -> int:
        before = len(self._tasks)
        self._tasks = [s for s in self._tasks if s.plugin != plugin]
        return before - len(self._tasks)

    def _due(self, sched: Schedule, now_ts: float) -> bool:
        if sched.interval is not None:
            return now_ts - sched.last_run >= sched.interval
        if sched.hour is not None:
            now = datetime.now()
            if (now.hour, now.minute) != (sched.hour, sched.minute):
                return False
            return now_ts - sched.last_run > 60  # 同一分钟内不重复触发
        return False

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            now = time.time()
            for sched in list(self._tasks):
                if not self._due(sched, now):
                    continue
                sched.last_run = now
                try:
                    result = sched.func(self.bot)
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    logger.exception("定时任务执行时摔了一跤喵: %s", sched.name)

    def describe(self) -> list[dict]:
        return [
            {
                "name": s.name,
                "plugin": s.plugin,
                "interval": s.interval,
                "time": f"{s.hour:02d}:{s.minute:02d}" if s.hour is not None else None,
            }
            for s in self._tasks
        ]


__all__ = ["Scheduler", "Schedule"]
