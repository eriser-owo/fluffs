"""OneBot 11 API 封装（NapCat 实现）。

常用接口都写成了方法；没写的接口可以直接用 ``api.call("动作名", 参数...)`` 调用，
例如 ``await bot.api.call("set_group_card", group_id=1, user_id=2, card="x")``。
"""

from __future__ import annotations

import logging
from typing import Any

from . import message as msg
from .errors import ActionFailed
from .events import Event, MessageEvent
from .transport import Transport

logger = logging.getLogger(__name__)


def _as_list(data: Any) -> list[dict[str, Any]]:
    """取出列表类接口的数组。

    标准 OneBot 11 里 ``get_group_list`` / ``get_friend_list`` 的 ``data`` 直接是数组；
    个别实现会再包一层 ``{"result": [...]}``，这里两种都兼容，其它形态返回空列表。
    """
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        inner = data.get("result")
        if isinstance(inner, list):
            return [item for item in inner if isinstance(item, dict)]
    logger.debug("列表接口回来的形状有点怪喵: %r", type(data).__name__)
    return []


class BotAPI:
    def __init__(self, transport: Transport, self_id: int = 0) -> None:
        self.transport = transport
        self.self_id = self_id

    # --- 通用 -------------------------------------------------------------
    async def call(self, action: str, timeout: float | None = None, **params: Any) -> Any:
        """调用任意 OneBot 动作，返回其 ``data``（对象或数组，取决于接口）。"""
        return await self.transport.call(action, params, timeout)

    def get_avatar_url(self, user_id: int | str, size: int = 640) -> str:
        """拼出某个 QQ 号的头像 CDN 地址
        发头像图：msg.image(bot.api.get_avatar_url(qq))；
        存字节：去 App 层的 bot.services["avatar_cache"] 下载。
        """
        from .avatar import avatar_url

        return avatar_url(user_id, size)

    # --- 消息 -------------------------------------------------------------
    async def send_group_msg(self, group_id: int, message: msg.MessageLike, *, auto_escape: bool = False) -> dict[str, Any]:
        return await self.call("send_group_msg", group_id=group_id, message=message, auto_escape=auto_escape)

    async def send_private_msg(self, user_id: int, message: msg.MessageLike, *, auto_escape: bool = False) -> dict[str, Any]:
        return await self.call("send_private_msg", user_id=user_id, message=message, auto_escape=auto_escape)

    async def send_msg(
        self,
        message: msg.MessageLike,
        *,
        group_id: int | None = None,
        user_id: int | None = None,
        auto_escape: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"message": message, "auto_escape": auto_escape}
        if group_id:
            params["message_type"] = "group"
            params["group_id"] = group_id
        elif user_id:
            params["message_type"] = "private"
            params["user_id"] = user_id
        return await self.call("send_msg", **params)

    async def delete_msg(self, message_id: int) -> dict[str, Any]:
        return await self.call("delete_msg", message_id=message_id)

    async def get_msg(self, message_id: int) -> dict[str, Any]:
        return await self.call("get_msg", message_id=message_id)

    async def reply(
        self,
        event: Event,
        message: msg.MessageLike,
        *,
        at_sender: bool = True,
        quote: bool = False,
        auto_escape: bool = False,
    ) -> dict[str, Any]:
        #reply to some msg
        if not isinstance(event, MessageEvent):
            raise ValueError("reply() 只能用于消息事件")

        parts: list[Any] = []
        if quote:
            parts.append(msg.reply(event.message_id))
        if at_sender and event.is_group:
            parts.append(msg.at(event.user_id))
            parts.append(" ")
        parts.append(message)
        payload = msg.build(*parts)

        if event.is_group:
            return await self.send_group_msg(event.group_id, payload, auto_escape=auto_escape)
        return await self.send_private_msg(event.user_id, payload, auto_escape=auto_escape)

    # --- 信息查询 ---------------------------------------------------------
    async def get_login_info(self) -> dict[str, Any]:
        return await self.call("get_login_info")

    async def get_status(self) -> dict[str, Any]:
        return await self.call("get_status")

    async def get_version_info(self) -> dict[str, Any]:
        return await self.call("get_version_info")

    async def get_group_list(self) -> list[dict[str, Any]]:
        """群列表。OneBot 11 里 ``data`` 本身就是数组。"""
        return _as_list(await self.call("get_group_list"))

    async def get_friend_list(self) -> list[dict[str, Any]]:
        """好友列表。同上，``data`` 是数组。"""
        return _as_list(await self.call("get_friend_list"))

    async def get_group_member_info(self, group_id: int, user_id: int, *, no_cache: bool = False) -> dict[str, Any]:
        return await self.call("get_group_member_info", group_id=group_id, user_id=user_id, no_cache=no_cache)

    async def get_group_member_list(self, group_id: int, *, no_cache: bool = False) -> list[dict[str, Any]]:
        """群成员列表。OneBot 11 里 ``data`` 本身就是数组。"""
        return _as_list(await self.call("get_group_member_list", group_id=group_id, no_cache=no_cache))

    # --- 群管理（后续管理类插件直接用）-----------------------------------
    async def set_group_ban(self, group_id: int, user_id: int, duration: int = 1800) -> dict[str, Any]:
        return await self.call("set_group_ban", group_id=group_id, user_id=user_id, duration=duration)

    async def set_group_whole_ban(self, group_id: int, enable: bool = True) -> dict[str, Any]:
        return await self.call("set_group_whole_ban", group_id=group_id, enable=enable)

    async def set_group_kick(self, group_id: int, user_id: int, *, reject_add_request: bool = False) -> dict[str, Any]:
        return await self.call("set_group_kick", group_id=group_id, user_id=user_id, reject_add_request=reject_add_request)

    async def send_group_poke(self, group_id: int, user_id: int) -> dict[str, Any]:
        """群内戳一戳（NapCat 扩展接口）。

        动作名各实现不一：NapCat 用 ``group_poke``，go-cqhttp 系叫 ``send_group_poke``。
        先试前者，失败再退后者；两个都不行就把第一个错误抛出去。
        """
        try:
            return await self.call("group_poke", group_id=group_id, user_id=user_id)
        except ActionFailed as first_error:
            try:
                return await self.call("send_group_poke", group_id=group_id, user_id=user_id)
            except ActionFailed:
                raise first_error from None

    # --- 请求处理 ---------------------------------------------------------
    async def set_friend_add_request(self, flag: str, approve: bool = True, remark: str = "") -> dict[str, Any]:
        return await self.call("set_friend_add_request", flag=flag, approve=approve, remark=remark)

    async def set_group_add_request(self, flag: str, sub_type: str, approve: bool = True, reason: str = "") -> dict[str, Any]:
        return await self.call("set_group_add_request", flag=flag, sub_type=sub_type, approve=approve, reason=reason)
