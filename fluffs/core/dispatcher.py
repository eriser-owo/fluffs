"""分发器：把事件路由到匹配的处理函数
处理顺序：先按事件大类（message / notice / request / meta_event / 通配 event）
再按priority升序执行
某个处理函数设置block=True时，后续处理函数不再执行（用于"拦截"式插件）
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..napcat.events import Event, MessageEvent, MetaEvent, NoticeEvent, RequestEvent
from .context import EventContext
from .rules import Rule

if TYPE_CHECKING:
    from .bot import FluffsBot

logger = logging.getLogger(__name__)

HandlerFunc = Callable[[EventContext], Awaitable[None] | None]

KIND_MESSAGE = "message"
KIND_NOTICE = "notice"
KIND_REQUEST = "request"
KIND_META = "meta_event"
KIND_ALL = "event"


def event_kind(event: Event) -> str:
    if isinstance(event, MessageEvent):
        return KIND_MESSAGE
    if isinstance(event, NoticeEvent):
        return KIND_NOTICE
    if isinstance(event, RequestEvent):
        return KIND_REQUEST
    if isinstance(event, MetaEvent):
        return KIND_META
    return KIND_ALL


@dataclass(slots=True)
class Handler:
    func: HandlerFunc
    rule: Rule | None = None
    priority: int = 10
    block: bool = False
    plugin: str | None = None
    kind: str = KIND_MESSAGE
    once: bool = False
    passive: bool = False  # 被动处理（只记录/观察，不主动回应）；黑名单用户的消息也会走到它
    name: str = ""

    def matches(self, ctx: EventContext) -> bool:
        if self.rule is None:
            return True
        try:
            return bool(self.rule(ctx))
        except Exception:
            logger.exception("规则判断绊了一下喵: handler=%s", self.name)
            return False


class Dispatcher:
    """处理函数注册表 + 分发器。"""

    def __init__(self) -> None:
        self._handlers: list[Handler] = []

    def register(
        self,
        kind: str,
        func: HandlerFunc,
        rule: Rule | None = None,
        *,
        priority: int = 10,
        block: bool = False,
        once: bool = False,
        plugin: str | None = None,
        passive: bool = False,
    ) -> Handler:
        handler = Handler(
            func=func,
            rule=rule,
            priority=priority,
            block=block,
            plugin=plugin,
            kind=kind,
            once=once,
            passive=passive,
            name=getattr(func, "__name__", repr(func)),
        )
        self._handlers.append(handler)
        self._handlers.sort(key=lambda h: h.priority)
        logger.debug("登记好一个处理器喵 [%s] %s（插件=%s, 优先级=%s）", kind, handler.name, plugin, priority)
        return handler

    def on(
        self,
        kind: str,
        rule: Rule | None = None,
        *,
        priority: int = 10,
        block: bool = False,
        once: bool = False,
        plugin: str | None = None,
        passive: bool = False,
    ) -> Callable[[HandlerFunc], HandlerFunc]:
        """装饰器工厂：拿到kind对应的注册装饰器。"""

        def decorator(func: HandlerFunc) -> HandlerFunc:
            self.register(kind, func, rule, priority=priority, block=block, once=once, plugin=plugin, passive=passive)
            return func

        return decorator

    # 各类事件的快捷入口（供 Bot 转发调用）
    def on_message(self, rule: Rule | None = None, **kwargs) -> Callable[[HandlerFunc], HandlerFunc]:
        return self.on(KIND_MESSAGE, rule, **kwargs)

    def on_notice(self, rule: Rule | None = None, **kwargs) -> Callable[[HandlerFunc], HandlerFunc]:
        return self.on(KIND_NOTICE, rule, **kwargs)

    def on_request(self, rule: Rule | None = None, **kwargs) -> Callable[[HandlerFunc], HandlerFunc]:
        return self.on(KIND_REQUEST, rule, **kwargs)

    def on_meta(self, rule: Rule | None = None, **kwargs) -> Callable[[HandlerFunc], HandlerFunc]:
        return self.on(KIND_META, rule, **kwargs)

    def on_event(self, rule: Rule | None = None, **kwargs) -> Callable[[HandlerFunc], HandlerFunc]:
        """任何事件都会走到（通配）"""
        return self.on(KIND_ALL, rule, **kwargs)

    # 卸载（插件热重载用）
    def remove_plugin(self, plugin: str) -> int:
        before = len(self._handlers)
        self._handlers = [h for h in self._handlers if h.plugin != plugin]
        return before - len(self._handlers)

    @property
    def handlers(self) -> list[Handler]:
        return list(self._handlers)

    # 分发
    async def dispatch(self, bot: "FluffsBot", event: Event) -> bool:
        """分发器核心，把事件交给匹配的处理器，返回是否有处理器执行过"""
        kind = event_kind(event)
        candidates = [h for h in self._handlers if h.kind in (kind, KIND_ALL)]
        if not candidates:
            return False

        # 黑名单用户的消息：只让 passive（记录/观察）处理器走，会回应的处理器全部跳过
        blacklisted = (
            isinstance(event, MessageEvent)
            and event.user_id in bot.config.bot.blacklist
        )

        handled = False
        for handler in candidates:
            if blacklisted and not handler.passive:
                continue
            ctx = EventContext(bot=bot, event=event, plugin=handler.plugin)
            if not handler.matches(ctx):
                continue
            handled = True
            try:
                result = handler.func(ctx)
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                logger.exception("处理器执行时摔了一跤喵: %s（插件=%s）", handler.name, handler.plugin)
            if handler.once:
                self._handlers.remove(handler)
            if handler.block:
                break
        return handled

    def describe(self, plugins: Iterable[str] | None = None) -> list[dict[str, object]]:
        """列出处理器信息（帮助插件 / 调试用）"""
        wanted = set(plugins) if plugins else None
        return [
            {"kind": h.kind, "name": h.name, "plugin": h.plugin, "priority": h.priority}
            for h in self._handlers
            if wanted is None or h.plugin in wanted
        ]


__all__ = [
    "KIND_ALL",
    "KIND_MESSAGE",
    "KIND_META",
    "KIND_NOTICE",
    "KIND_REQUEST",
    "Dispatcher",
    "Handler",
    "HandlerFunc",
    "event_kind",
]
