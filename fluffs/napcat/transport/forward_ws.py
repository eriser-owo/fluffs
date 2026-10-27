"""正向 WebSocket：本 Bot 作为客户端，主动连接 NapCat 的 WS 服务端。

NapCat 侧配置（网络配置 -> 新建 -> WebSocket 客户端）：
    地址: ws://127.0.0.1:3001
    Token: 与 config.toml 的 connection.token 一致
本 Bot 侧：connection.mode = "forward_ws"，connection.forward_url 填上面地址。

自带断线重连。注意：该模式尚未在真实 NapCat 上验证，首次使用请留意日志。
"""

from __future__ import annotations

import asyncio
import logging

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from .base import EventHandler, NotConnected, StateHandler, Transport

logger = logging.getLogger(__name__)


class ForwardWebSocketTransport(Transport):
    def __init__(self, config, on_event: EventHandler, on_state_change: StateHandler | None = None) -> None:
        super().__init__(config, on_event, on_state_change)
        self._conn: ClientConnection | None = None
        self._runner: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self._runner = asyncio.create_task(self._run_forever(), name="forward-ws")
        logger.info("正向 WS 客户端出发啦喵 目标: %s", self.config.forward_url)

    async def stop(self) -> None:
        self._stopping = True
        if self._runner is not None:
            self._runner.cancel()
            await asyncio.gather(self._runner, return_exceptions=True)
            self._runner = None
        conn, self._conn = self._conn, None
        if conn is not None:
            await conn.close()
        await self._set_ready(False)
        await self._cancel_tasks()

    async def _send_text(self, text: str) -> None:
        conn = self._conn
        if conn is None:
            raise NotConnected("尚未连接到 NapCat")
        try:
            await conn.send(text)
        except ConnectionClosed as exc:
            raise NotConnected("NapCat 连接已断开") from exc

    async def _run_forever(self) -> None:
        headers = {}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"

        while not self._stopping:
            try:
                async with connect(
                    self.config.forward_url,
                    additional_headers=headers,
                    ping_interval=30,
                    ping_timeout=30,
                    max_size=None,
                ) as connection:
                    self._conn = connection
                    await self._set_ready(True)
                    try:
                        async for raw in connection:
                            await self._handle_text(raw)
                    finally:
                        self._conn = None
                        await self._set_ready(False)
                        self._fail_pending(NotConnected("NapCat 连接已断开"))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("这次没连上 NapCat 喵，眨个眼再试~: %s", exc)

            if not self._stopping:
                await asyncio.sleep(max(self.config.reconnect_interval, 0.5))
