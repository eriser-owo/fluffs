"""识图 / 引用内容辅助。
取「被回复消息」的文本与图片，把图片转成 base64 data URL，构造多模态消息。
"""

from __future__ import annotations

import base64

import httpx

from fluffs.onebot11 import message as msg
from fluffs.onebot11.events import MessageEvent

from .providers import ChatMessage


def _guess_mime(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG"):
        return "image/png"
    if raw.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if raw.startswith(b"GIF"):
        return "image/gif"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _data_url(raw: bytes) -> str:
    return f"data:{_guess_mime(raw)};base64," + base64.b64encode(raw).decode()


async def resolve_reference(event: MessageEvent, api) -> tuple[dict | None, str]:
    """返回 (要识别的图段, 被回复消息的文本)。

    图段优先取当前消息里的图，其次取回复引用的图；被回复消息的文本单独返回。
    """
    current_image = None
    segs = event.get_segments("image")
    if segs:
        current_image = segs[0]

    quoted_image = None
    quoted_text = ""
    reply_segs = event.get_segments("reply")
    if reply_segs:
        raw_id = reply_segs[0].get("data", {}).get("id")
        try:
            quoted = await api.get_msg(int(raw_id))
        except Exception:
            quoted = None
        if quoted:
            qmsg = quoted.get("message") or []
            img_segs = msg.extract(qmsg, "image")
            quoted_image = img_segs[0] if img_segs else None
            quoted_text = msg.to_plain(qmsg).strip()

    return (current_image or quoted_image, quoted_text)


async def image_data_url(api, segment: dict, timeout: float = 15.0) -> str | None:
    """把一个 image 段转成 data URL；拿不到返回 None。"""
    data = segment.get("data") or {}
    file = str(data.get("file") or "")
    url = str(data.get("url") or "")

    #对端直接给 base64
    if file.startswith("base64://"):
        try:
            raw = base64.b64decode(file[len("base64://"):])
            return _data_url(raw)
        except Exception:
            return None

    # 本地 / 远程 URL → 下载
    if url.startswith("http://") or url.startswith("https://"):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return _data_url(resp.content)
        except Exception:
            return None

    return None


def build_vision_message(text: str, data_url: str, quoted_text: str = "") -> ChatMessage:
    """构造多模态 user 消息：文字 + 图片。"""
    parts = []
    if quoted_text:
        parts.append(f"回复的消息内容：{quoted_text}")
    parts.append(text or "请描述一下这张图片")
    question = "\n".join(parts)
    return ChatMessage("user", [
        {"type": "text", "text": question},
        {"type": "image_url", "image_url": {"url": data_url}},
    ])


__all__ = ["build_vision_message", "image_data_url", "resolve_reference"]
