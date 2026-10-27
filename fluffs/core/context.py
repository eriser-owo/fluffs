"""事件上下文：传给每个处理函数的对象。

处理函数统一签名 async def handler(ctx: EventContext) -> None；
通过 ctx 拿到事件、Bot、命令参数，并用 ctx.reply 快速回复
后续要加功能（权限校验、限流、会话状态）在 state / 本类上扩展
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..napcat import message as msg
from ..napcat.events import Event, MessageEvent

if TYPE_CHECKING:
    from .bot import FluffsBot


@dataclass(slots=True)
class EventContext:
    bot: "FluffsBot"
    event: Event
    plugin: str | None = None
    state: dict[str, Any] = field(default_factory=dict)

    @property
    def message_event(self) -> MessageEvent | None:
        """消息事件（非消息事件返回 None）"""
        return self.event if isinstance(self.event, MessageEvent) else None

    @property
    def text(self) -> str:
        """消息事件的纯文本（非消息事件返回空串）"""
        event = self.message_event
        return event.plain_text if event else ""

    # 规则写入的状态
    @property
    def command(self) -> str | None:
        """命中的命令名（由rules.command写入）。"""
        return self.state.get("command")

    @property
    def args(self) -> str:
        """命令后面的原始参数串"""
        return str(self.state.get("args") or "")

    @property
    def argv(self) -> list[str]:
        """参数按空白切分后的列表"""
        return self.args.split()

    @property
    def match(self):
        """rules.regex命中的 Match 对象"""
        return self.state.get("match")

    # 回复
    async def reply(self, message: msg.MessageLike, at_sender: bool = True, **kwargs: Any) -> dict[str, Any]:
        """回复当前消息（群里默认带上 @）"""
        return await self.bot.api.reply(self.event, message, at_sender=at_sender, **kwargs)

    async def send(self, message: msg.MessageLike, **kwargs: Any) -> dict[str, Any]:
        """发送到当前会话（不 @ 发送者）"""
        return await self.bot.api.reply(self.event, message, at_sender=False, **kwargs)
