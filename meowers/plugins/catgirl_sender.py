"""插件：发「来点猫娘」，回复一张 nekos.moe 的猫娘图（屏蔽 NSFW）。"""

from __future__ import annotations

import logging

import httpx

from fluffs.core import EventContext, rules
from fluffs.onebot11 import message as msg

logger = logging.getLogger(__name__)

__plugin_meta__ = {
    "name": "catgirl_sender",
    "description": "发「来点猫娘」随机回复一张 nekos.moe 猫娘图",
    "usage": "来点猫娘",
    "version": "0.1.0",
    "author": "eriser-owo",
}

_API = "https://nekos.moe/api/v1/random/image"
_MAX_RETRY = 3
_TIMEOUT = 15.0


async def _random_catgirl() -> tuple[str, str] | None:
    """拉一张猫娘图，返回 (图片URL, 作者名)；失败返回 None。"""
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        for _ in range(_MAX_RETRY):
            resp = await client.get(_API, params={"count": 1, "nsfw": "false"})
            resp.raise_for_status()
            images = resp.json().get("images") or []
            if not images:
                return None
            image = images[0]
            if image.get("nsfw"):
                continue
            url = image.get("image_url") or ""
            if not url and image.get("id"):
                url = f"https://nekos.moe/image/{image['id']}"
            if not url:
                continue
            artist = image.get("artist") or ""
            if isinstance(artist, dict):
                artist = artist.get("name") or ""
            return url, str(artist)
    return None


def setup(bot) -> None:
    @bot.on_message(rules.regex(r"^\s*来点猫娘\s*$"), priority=50)
    async def on_catgirl(ctx: EventContext) -> None:
        try:
            result = await _random_catgirl()
        except Exception:
            logger.exception("拉图娘翻车啦喵")
            await ctx.send("猫娘暂时离家出走了喵，稍后再试~")
            return
        if result is None:
            await ctx.send("没找到合适的猫娘喵，稍后再试~")
            return
        url, artist = result
        caption = f"作者: {artist}" if artist else ""
        await ctx.send(msg.build(caption, msg.image(url)))
