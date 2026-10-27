"""传输层抽象：与 NapCat 之间的 OneBot 11 JSON over WebSocket。

一个 Transport 同时负责两件事：
1. 接收 NapCat 上报的事件（交给 ``on_event`` 回调）；
2. 发送 API 调用并按 ``echo`` 匹配回包（``call``）。

实现见 ``reverse_ws.py`` / ``forward_ws.py``；异常类型在 ``napcat/errors.py``。
扩展新的传输方式（如 HTTP POST + HTTP API）只需继承 ``Transport``。
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from ...config import ConnectionConfig
from ..errors import ActionFailed, ActionTimeout, NotConnected, OneBotError

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]
StateHandler = Callable[[bool], Awaitable[None] | None]


class Transport(ABC):
    """WebSocket 传输基类。"""

    def __init__(
        self,
        config: ConnectionConfig,
        on_event: EventHandler,
        on_state_change: StateHandler | None = None,
    ) -> None:
        self.config = config
        self._on_event = on_event
        self._on_state_change = on_state_change
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._tasks: set[asyncio.Task[Any]] = set()
        self._counter = itertools.count(1)
        self._ready = False

    # --- 生命周期 ---------------------------------------------------------
    @abstractmethod
    async def start(self) -> None:
        """开始监听 / 连接。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止并释放资源。"""

    @abstractmethod
    async def _send_text(self, text: str) -> None:
        """把一段 JSON 文本发出去；未连接时应抛 ``NotConnected``。"""

    # --- 状态 -------------------------------------------------------------
    @property
    def ready(self) -> bool:
        """是否有可用连接。"""
        return self._ready

    async def _set_ready(self, value: bool) -> None:
        """更新连接状态并通知上层。

        注意：这里不做"状态相同就跳过"的去重——一旦回调里 await 了耗时操作，
        去重会让下一次连接拿到残留状态，导致状态与回调都不触发。
        因此回调方必须保证自己不做阻塞收包循环的事情（见 core.bot 的说明）。
        """
        self._ready = value
        logger.info("NapCat 连线状态: %s 喵", "已连接" if value else "已断开")
        if self._on_state_change is not None:
            result = self._on_state_change(value)
            if asyncio.iscoroutine(result):
                await result

    # --- API 调用 ---------------------------------------------------------
    async def call(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """调用一个 OneBot API，返回其中的 ``data`` 字段。

        注意：``data`` 的形态由接口决定——多数是对象，但 ``get_group_list`` /
        ``get_friend_list`` 等**直接就是数组**，所以这里原样返回、不做 dict 强制转换
        （早期版本把非 dict 的 data 吞成 ``{}``，导致列表类接口永远返回空）。
        """
        if not self._ready:
            raise NotConnected(f"未连接到 NapCat，无法调用 {action}")

        echo = f"{action}:{next(self._counter)}"
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[echo] = future
        payload = {"action": action, "params": params or {}, "echo": echo}
        wait_timeout = self.config.api_timeout if timeout is None else timeout

        try:
            await self._send_text(json.dumps(payload, ensure_ascii=False))
            response = await asyncio.wait_for(future, wait_timeout)
        except TimeoutError as exc:
            raise ActionTimeout(action, wait_timeout) from exc
        finally:
            self._pending.pop(echo, None)

        retcode = response.get("retcode", 0)
        if response.get("status") == "failed" or (isinstance(retcode, int) and retcode != 0):
            raise ActionFailed(action, retcode, str(response.get("message") or ""), str(response.get("wording") or ""), echo)

        data = response.get("data")
        return {} if data is None else data

    # --- 收包 -------------------------------------------------------------
    async def _handle_text(self, text: str) -> None:
        """解析一条入站报文：API 回包 or 事件上报。"""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("这条报文不是 JSON 呀，悄悄丢掉喵: %.200s", text)
            return
        if not isinstance(payload, dict):
            return

        echo = payload.get("echo")
        if echo is not None and echo in self._pending:
            future = self._pending.pop(echo)
            if not future.done():
                future.set_result(payload)
            return

        if "post_type" in payload:
            self._spawn(self._dispatch_event(payload))
            return

        logger.debug("这条报文我看不懂喵，先跳过~: %.200s", payload)

    async def _dispatch_event(self, raw: dict[str, Any]) -> None:
        try:
            result = self._on_event(raw)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.exception("事件处理失败喵: post_type=%s", raw.get("post_type"))

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _fail_pending(self, exc: Exception) -> None:
        """连接断开时让所有在途调用立刻失败，避免插件一直挂着。"""
        pending, self._pending = self._pending, {}
        for future in pending.values():
            if not future.done():
                future.set_exception(exc)

    async def _cancel_tasks(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()


__all__ = [
    "ActionFailed",
    "ActionTimeout",
    "EventHandler",
    "NotConnected",
    "OneBotError",
    "StateHandler",
    "Transport",
]
