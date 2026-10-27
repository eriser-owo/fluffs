"""反向 WebSocket：本 Bot 作为服务端，NapCat 主动连接。
NapCat 侧配置（网络配置 -> 新建 -> WebSocket 服务器(反向)）：
    URL:   ws://127.0.0.1:8080/onebot/v11/ws
    Token: 与 config.toml 的 connection.token 一致（留空则不校验）
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlparse

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

from .base import EventHandler, NotConnected, StateHandler, Transport

logger = logging.getLogger(__name__)


class ReverseWebSocketTransport(Transport):
    def __init__(self, config, on_event: EventHandler, on_state_change: StateHandler | None = None) -> None:
        super().__init__(config, on_event, on_state_change)
        self._server: Server | None = None
        self._conn: ServerConnection | None = None

    async def start(self) -> None:
        self._server = await serve(
            self._handler,
            self.config.host,
            self.config.port,
            process_request=self._process_request,
            ping_interval=30,
            ping_timeout=30,
            max_size=None,  # 图片等大消息不限制
        )
        logger.info(
            "反向 WS 小门开好啦喵 地址: ws://%s:%s%s 快来快来~",
            self.config.host,
            self.config.port,
            self.config.path,
        )

    async def stop(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            await conn.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        await self._set_ready(False)
        await self._cancel_tasks()
        logger.info("反向 WS 小门关上啦喵，下次再开~")

    async def _send_text(self, text: str) -> None:
        conn = self._conn
        if conn is None:
            raise NotConnected("NapCat 尚未连接")
        try:
            await conn.send(text)
        except ConnectionClosed as exc:
            raise NotConnected("NapCat 连接已断开") from exc

    # --- 握手校验 ---------------------------------------------------------
    async def _process_request(self, connection: ServerConnection, request: Request) -> Response | None:
        parsed = urlparse(request.path)
        if self.config.path and parsed.path != self.config.path:
            logger.warning("抱歉喵，路径不对不给进~ %s", request.path)
            return connection.respond(404, "Not Found\n")
        if self.config.token and not self._check_token(parsed.query, request):
            logger.warning("token 对不上呀，不能放进来喵 来源: %s", connection.remote_address)
            return connection.respond(401, "Unauthorized\n")
        return None

    def _check_token(self, query: str, request: Request) -> bool:
        expected = self.config.token
        if parse_qs(query).get("access_token", [""])[0] == expected:
            return True
        auth = request.headers.get("Authorization", "")
        if auth.removeprefix("Bearer ").strip() == expected:
            return True
        return False

    # --- 连接处理 ---------------------------------------------------------
    async def _handler(self, connection: ServerConnection) -> None:
        logger.info("NapCat 牵上手啦喵 (%s)", connection.remote_address)
        if self._conn is not None and self._conn is not connection:
            logger.warning("旧连接还在呀，先请它下去再收新的喵（NapCat 重连中）")
            await self._conn.close()
        self._conn = connection
        await self._set_ready(True)
        try:
            async for raw in connection:
                await self._handle_text(raw)
        except ConnectionClosed:
            pass
        finally:
            if self._conn is connection:
                self._conn = None
                await self._set_ready(False)
            self._fail_pending(NotConnected("NapCat 连接已断开"))
