"""消息段（OneBot 11 CQ 码数组）构造与解析工具。

OneBot 11 的消息有两种形态，取决于 NapCat 的「消息格式」设置：

1. **数组**（推荐）：``[{"type": "text", "data": {"text": "你好"}}, {"type": "at", "data": {"qq": "123"}}]``
2. **CQ 码字符串**：``"[CQ:at,qq=123] 你好"``

本模块两种都吃：``to_segments`` 遇到字符串会调用 ``from_cq_string`` 解析成数组，
所以 ``plain_text`` / ``at_user_ids`` 在任何格式下都能正确工作（否则 @ 判定会失效）。
对外构造消息统一用数组形式。
"""

from __future__ import annotations

import re
from typing import Any

Segment = dict[str, Any]
MessageLike = str | list[Segment]

#: 匹配一个 CQ 码：[CQ:type,key=value,...]
_CQ_PATTERN = re.compile(r"\[CQ:([^,\]]+)((?:,[^\]]*)?)\]")

#: OneBot 11 规定转义的四个字符（反转义时 &amp; 必须最后处理）
_UNESCAPE = (("&#44;", ","), ("&#91;", "["), ("&#93;", "]"), ("&amp;", "&"))
_ESCAPE = (("&", "&amp;"), ("[", "&#91;"), ("]", "&#93;"), (",", "&#44;"))


def unescape(text: str) -> str:
    """反转义 CQ 码里的实体（&#91; -> [ 等）。"""
    for entity, char in _UNESCAPE:
        text = text.replace(entity, char)
    return text


def escape(text: str) -> str:
    """转义成 CQ 码里的实体（[ -> &#91; 等）。"""
    for char, entity in _ESCAPE:
        text = text.replace(char, entity)
    return text


def from_cq_string(raw: str) -> list[Segment]:
    """把 CQ 码字符串解析成消息段数组；普通文本则得到单个 text 段。"""
    segments: list[Segment] = []
    cursor = 0
    for match in _CQ_PATTERN.finditer(raw):
        if match.start() > cursor:
            segments.extend(_text_segments(raw[cursor:match.start()]))
        seg_type = match.group(1)
        data: dict[str, str] = {}
        for pair in match.group(2).lstrip(",").split(","):
            if not pair:
                continue
            key, _, value = pair.partition("=")
            if key:
                data[key.strip()] = unescape(value)
        segments.append({"type": seg_type, "data": data})
        cursor = match.end()
    if cursor < len(raw):
        segments.extend(_text_segments(raw[cursor:]))
    return segments


def _text_segments(raw: str) -> list[Segment]:
    """CQ 码之间的普通文本（反转义后转成 text 段）。"""
    content = unescape(raw)
    return [text(content)] if content else []


def segment(seg_type: str, **data: Any) -> Segment:
    """构造任意消息段，例如 ``segment("image", file="xxx.jpg")``。"""
    return {"type": seg_type, "data": {k: v for k, v in data.items() if v is not None}}


def text(content: str) -> Segment:
    return segment("text", text=content)


def at(user_id: int | str) -> Segment:
    return segment("at", qq=str(user_id))


def at_all() -> Segment:
    return segment("at", qq="all")


def face(face_id: int) -> Segment:
    return segment("face", id=str(face_id))


def image(file: str) -> Segment:
    """file 支持本地路径、http(s) 链接或 base64:// 。"""
    return segment("image", file=file)


def reply(message_id: int | str) -> Segment:
    return segment("reply", id=str(message_id))


def build(*parts: Any) -> list[Segment]:
    """把若干片段拼成消息段数组：字符串会变成 text 段，字典原样保留。"""
    message: list[Segment] = []
    for part in parts:
        if part is None or part == "":
            continue
        if isinstance(part, str):
            message.append(text(part))
        elif isinstance(part, dict):
            message.append(part)
        elif isinstance(part, (list, tuple)):
            message.extend(build(*part))
        else:
            message.append(text(str(part)))
    return message


def to_segments(message: MessageLike) -> list[Segment]:
    """把字符串（CQ 码）或数组统一成消息段数组。"""
    if isinstance(message, str):
        return from_cq_string(message) if message else []
    return [seg for seg in message if isinstance(seg, dict)]


def to_plain(message: MessageLike) -> str:
    """提取纯文本（忽略图片、表情等非文本段）。"""
    return "".join(
        str(seg.get("data", {}).get("text", ""))
        for seg in to_segments(message)
        if seg.get("type") == "text"
    )


def extract(message: MessageLike, seg_type: str) -> list[Segment]:
    """取出指定类型的消息段。"""
    return [seg for seg in to_segments(message) if seg.get("type") == seg_type]
