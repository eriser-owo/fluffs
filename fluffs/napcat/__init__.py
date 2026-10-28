"""OneBot 11 协议层：与 NapCat 之间的全部协议细节。

这一层只关心"协议"，不关心业务：
    events.py      上报事件的模型与解析
    message.py     消息段（CQ 数组）的构造与提取
    api.py         OneBot 动作（API）封装
    transport/     连接与收发（反向 / 正向 WebSocket）
    errors.py      协议层异常

依赖方向：``napcat`` 只依赖 ``config``，不认识 ``core`` / ``modules``。
插件里需要事件类型或消息段时从这里 import：
    from fluffs.napcat import MessageEvent, NoticeEvent
    from fluffs.napcat import message as msg
"""

from __future__ import annotations

from . import message
from .api import BotAPI
from .avatar import AVATAR_SIZES, avatar_url
from .errors import ActionFailed, ActionTimeout, NotConnected, OneBotError
from .events import (
    Event,
    GroupMessageEvent,
    MessageEvent,
    MetaEvent,
    NoticeEvent,
    PrivateMessageEvent,
    RequestEvent,
    parse_event,
)
from .transport import Transport, create_transport

__all__ = [
    "AVATAR_SIZES",
    "ActionFailed",
    "ActionTimeout",
    "BotAPI",
    "Event",
    "GroupMessageEvent",
    "MessageEvent",
    "MetaEvent",
    "NotConnected",
    "NoticeEvent",
    "OneBotError",
    "PrivateMessageEvent",
    "RequestEvent",
    "Transport",
    "avatar_url",
    "create_transport",
    "message",
    "parse_event",
]
