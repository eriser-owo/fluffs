"""群友头像缓存模块：把 qlogo 头像下载到本地磁盘

    cache.py   下载 + 磁盘缓存
    __init__   装配：实例挂到 bot.services["avatar_cache"]

缓存目录 data/avatars/{QQ}_{size}.jpg，默认 7 天过期后重拉
    cache = bot.services["avatar_cache"]
    data = await cache.get(event.user_id)
"""

from __future__ import annotations

import logging

from ...config import APP_ROOT
from .cache import AvatarCache, DEFAULT_SIZE, DEFAULT_TTL

logger = logging.getLogger(__name__)

__plugin_meta__ = {
    "name": "avatar_cache",
    "description": "群友头像下载与磁盘缓存",
    "usage": "无",
    "version": "0.1.0",
}


async def setup(bot) -> None:
    cache = AvatarCache(base_dir=APP_ROOT)
    bot.services["avatar_cache"] = cache
    logger.info("头像缓存就位啦喵 目录=%s", cache.dir)

    async def teardown(_bot) -> None:
        bot.services.pop("avatar_cache", None)
        await cache.aclose()

    bot.on_teardown(teardown)


__all__ = ["AvatarCache", "DEFAULT_SIZE", "DEFAULT_TTL", "setup"]
