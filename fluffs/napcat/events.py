"""OneBot 11 上报事件的数据模型。

只建模常用字段，其余原始字段保留在 ``Event.raw`` 中，
可通过 ``event.get("xxx")`` 或 ``event.raw["xxx"]`` 访问（便于后续扩展）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import message as msg


@dataclass(slots=True)
class Event:
    """所有上报事件的基类。"""

    time: int = 0
    self_id: int = 0
    post_type: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def get(self, key: str, default: Any = None) -> Any:
        """读取未建模的原始字段。"""
        return self.raw.get(key, default)

    @property
    def is_message(self) -> bool:
        return self.post_type == "message"

    @property
    def is_notice(self) -> bool:
        return self.post_type == "notice"

    @property
    def is_request(self) -> bool:
        return self.post_type == "request"

    @property
    def is_meta(self) -> bool:
        return self.post_type == "meta_event"


@dataclass(slots=True)
class MessageEvent(Event):
    """消息事件（群 / 私聊）。"""

    message_type: str = ""  # group | private
    sub_type: str = ""
    message_id: int = 0
    user_id: int = 0
    message: msg.MessageLike = field(default_factory=list)
    raw_message: str = ""
    font: int = 0
    sender: dict[str, Any] = field(default_factory=dict)
    group_id: int = 0  # 私聊为 0

    # --- 便捷属性 ---------------------------------------------------------
    @property
    def is_group(self) -> bool:
        return self.message_type == "group"

    @property
    def is_private(self) -> bool:
        return self.message_type == "private"

    @property
    def segments(self) -> list[msg.Segment]:
        return msg.to_segments(self.message)

    @property
    def plain_text(self) -> str:
        """消息中的纯文本部分。"""
        return msg.to_plain(self.message)

    @property
    def at_user_ids(self) -> list[int]:
        """被 @ 的 QQ 号（包含 at_all 时返回 -1 作为标记）。"""
        result: list[int] = []
        for seg in msg.extract(self.message, "at"):
            qq = str(seg.get("data", {}).get("qq", ""))
            if qq == "all":
                result.append(-1)
            elif qq.isdigit():
                result.append(int(qq))
        return result

    @property
    def is_at_all(self) -> bool:
        return -1 in self.at_user_ids

    @property
    def nickname(self) -> str:
        return str(self.sender.get("card") or self.sender.get("nickname") or self.user_id)

    @property
    def role(self) -> str:
        return str(self.sender.get("role") or ("member" if self.is_group else ""))

    @property
    def role_cn(self) -> str:
        return {"owner": "群主", "admin": "管理员", "member": "成员"}.get(self.role, "未知")

    def get_segments(self, seg_type: str) -> list[msg.Segment]:
        return msg.extract(self.message, seg_type)

    @property
    def images(self) -> list[str]:
        return [str(seg.get("data", {}).get("url") or seg.get("data", {}).get("file")) for seg in self.get_segments("image")]


@dataclass(slots=True)
class GroupMessageEvent(MessageEvent):
    message_type: str = "group"
    anonymous: dict[str, Any] | None = None


@dataclass(slots=True)
class PrivateMessageEvent(MessageEvent):
    message_type: str = "private"


@dataclass(slots=True)
class NoticeEvent(Event):
    """通知事件：戳一戳、群成员增减、撤回等。"""

    notice_type: str = ""
    sub_type: str = ""
    user_id: int = 0
    group_id: int = 0
    operator_id: int = 0
    target_id: int = 0
    message_id: int = 0


@dataclass(slots=True)
class RequestEvent(Event):
    """请求事件：加好友 / 加群。"""

    request_type: str = ""
    sub_type: str = ""
    user_id: int = 0
    group_id: int = 0
    comment: str = ""
    flag: str = ""


@dataclass(slots=True)
class MetaEvent(Event):
    """元事件：生命周期、心跳。"""

    meta_event_type: str = ""
    sub_type: str = ""
    interval: int = 0


def _as_int(value: Any, default: int = 0) -> int:
    """宽松取整。

    字段可能是 int，也可能是字符串（不同实现的 QQ 号/ID 有时是字符串）；
    遇到缺失或意外格式时返回默认值，**不让一个坏字段把整条事件丢掉**。
    """
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return default


def _base(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "time": _as_int(raw.get("time")),
        "self_id": _as_int(raw.get("self_id")),
        "post_type": str(raw.get("post_type") or ""),
        "raw": raw,
    }


def parse_event(raw: dict[str, Any]) -> Event:
    """把 NapCat 上报的原始 dict 解析成事件对象。"""
    post_type = str(raw.get("post_type") or "")

    if post_type == "message":
        group_id = _as_int(raw.get("group_id"))
        message_type = str(raw.get("message_type") or ("group" if group_id else "private"))
        common: dict[str, Any] = {
            **_base(raw),
            "message_type": message_type,
            "sub_type": str(raw.get("sub_type") or ""),
            "message_id": _as_int(raw.get("message_id")),
            "user_id": _as_int(raw.get("user_id")),
            # 个别实现只给 raw_message（CQ 码字符串）；那时用它兜底，
            # 否则 plain_text 会是空的、关键词与 @ 判定全部失效
            "message": raw.get("message") or raw.get("raw_message") or "",
            "raw_message": str(raw.get("raw_message") or ""),
            "font": _as_int(raw.get("font")),
            "sender": raw.get("sender") or {},
            "group_id": group_id,
        }
        if message_type == "group":
            return GroupMessageEvent(**common, anonymous=raw.get("anonymous"))
        return PrivateMessageEvent(**common)

    if post_type == "notice":
        return NoticeEvent(
            **_base(raw),
            notice_type=str(raw.get("notice_type") or ""),
            sub_type=str(raw.get("sub_type") or ""),
            user_id=_as_int(raw.get("user_id")),
            group_id=_as_int(raw.get("group_id")),
            operator_id=_as_int(raw.get("operator_id")),
            target_id=_as_int(raw.get("target_id")),
            message_id=_as_int(raw.get("message_id")),
        )

    if post_type == "request":
        return RequestEvent(
            **_base(raw),
            request_type=str(raw.get("request_type") or ""),
            sub_type=str(raw.get("sub_type") or ""),
            user_id=_as_int(raw.get("user_id")),
            group_id=_as_int(raw.get("group_id")),
            comment=str(raw.get("comment") or ""),
            flag=str(raw.get("flag") or ""),
        )

    if post_type == "meta_event":
        return MetaEvent(
            **_base(raw),
            meta_event_type=str(raw.get("meta_event_type") or ""),
            sub_type=str(raw.get("sub_type") or ""),
            interval=_as_int(raw.get("interval")),
        )

    return Event(**_base(raw))
