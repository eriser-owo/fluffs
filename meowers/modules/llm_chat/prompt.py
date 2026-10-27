"""模型输入的组装：把一条 QQ 消息压成给模型看的文本。

格式固定为（私聊没有职位与群号）：

    昵称: 测试群名片
    职位: 管理员
    群号: 123456
    消息: 帮我写一句祝福

这样模型能同时看到"谁说的、什么身份、说了什么"，而不用把整个聊天记录塞给它。
"""

from __future__ import annotations

from fluffs.napcat import MessageEvent  # 走包级导出，不深挖框架子模块


def build_user_input(event: MessageEvent) -> str:
    lines = [f"昵称: {event.nickname}"]
    if event.is_group:
        lines.append(f"职位: {event.role_cn}")
        lines.append(f"群号: {event.group_id}")
    lines.append(f"消息: {event.plain_text.strip()}")
    return "\n".join(lines)


__all__ = ["build_user_input"]
