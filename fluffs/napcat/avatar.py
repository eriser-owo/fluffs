"""QQ 头像 URL 构造
https://q1.qlogo.cn/g?b=qq&nk={QQ号}&s={尺寸}
``s`` 常见取值 40 / 100 / 140 / 640，``s=0`` 表示原图
返回的 URL 可直接交给 ``message.image(url)`` 发图
若要拿到字节用于本地合成（Pillow 等），去 App 层的 meowers.modules.avatar_cache 下载并缓存
"""

from __future__ import annotations

#: qlogo 常用尺寸（像素）。640 是常用大头像；0 表示原图，但格式不保证是 JPEG
AVATAR_SIZES = (40, 100, 140, 640)

_QLOGO_TEMPLATE = "https://q1.qlogo.cn/g?b=qq&nk={user_id}&s={size}"


def avatar_url(user_id: int | str, size: int = 640) -> str:
    """按 QQ 号拼出头像 CDN 地址，size建议用AVATAR_SIZES里的值。"""
    return _QLOGO_TEMPLATE.format(user_id=int(user_id), size=int(size))


__all__ = ["AVATAR_SIZES", "avatar_url"]
