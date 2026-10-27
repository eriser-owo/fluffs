"""规则（Rule）：判断某个事件是否该由某个处理函数处理。
Rule 就是一个Callable[[EventContext], bool]，可以用 all_of/any_of/negate自由组合。
规则可以顺手往ctx.state里写解析结果
（例如command会写入命令名与参数）。
这里只放通用原语：命中方式（命令、正则、@、群/私聊、超级用户）。
业务性的匹配（关键词自动回复分支）在 App 的关键词模块（如meowers.modules.kw_reply）
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from ..napcat.events import MessageEvent, NoticeEvent, RequestEvent
from .context import EventContext

Rule = Callable[[EventContext], bool]


# 组合子
def all_of(*rules: Rule) -> Rule:
    """全部满足，相当于AND"""
    return lambda ctx: all(rule(ctx) for rule in rules)


def any_of(*rules: Rule) -> Rule:
    """任一满足，相当于OR"""
    return lambda ctx: any(rule(ctx) for rule in rules)


def negate(rule: Rule) -> Rule:
    """取反，相当于NOT"""
    return lambda ctx: not rule(ctx)


def always(ctx: EventContext) -> bool:
    return True


# 事件类别
def message_only(ctx: EventContext) -> bool:
    return isinstance(ctx.event, MessageEvent)


def notice_only(ctx: EventContext) -> bool:
    return isinstance(ctx.event, NoticeEvent)


def request_only(ctx: EventContext) -> bool:
    return isinstance(ctx.event, RequestEvent)


def group_only(ctx: EventContext) -> bool:
    """仅群聊消息"""
    event = ctx.event
    return isinstance(event, MessageEvent) and event.is_group


def private_only(ctx: EventContext) -> bool:
    """仅私聊消息。"""
    event = ctx.event
    return isinstance(event, MessageEvent) and event.is_private


def scope(where: str) -> Rule:
    """按会话类型取规则：group/private/all"""
    mapping = {"group": group_only, "private": private_only, "all": always}
    try:
        return mapping[where]
    except KeyError:
        raise ValueError(f"未知的会话范围 {where!r}，可选: {', '.join(mapping)}") from None


# @ 与身份
def to_me(*, allow_private: bool = True, allow_at_all: bool = True) -> Rule:
    """是否在跟机器人说话：群聊里@了机器人（或@全体），私聊默认算。
    判定用的机器人QQ号优先取事件自带的self_id，它随每条上报一起到达。
    不依赖 get_login_info 是否已经返回，避免"刚连上时前几条消息 @ 判定失败"。
    """

    def _rule(ctx: EventContext) -> bool:
        event = ctx.message_event
        if event is None:
            return False
        if event.is_private:
            return allow_private
        if event.is_at_all and allow_at_all:
            return True
        self_id = event.self_id or ctx.bot.api.self_id or ctx.bot.config.bot.self_id
        return bool(self_id) and self_id in event.at_user_ids

    return _rule


def from_superuser() -> Rule:
    """发送者在config.bot.superusers中"""
    def _rule(ctx: EventContext) -> bool:
        event = ctx.message_event
        if event is None:
            return False
        return event.user_id in ctx.bot.config.bot.superusers
    return _rule


# 文本
def command(*names: str, prefixes: Iterable[str] | None = None, ignore_case: bool = False) -> Rule:
    """命令匹配，例如 command("echo", "复读") 匹配 /echo 你好。

    命中后会把命令名写进 ctx.state["command"]，参数写进 ctx.state["args"]；
    prefixes 省略时使用 config.bot.command_prefixes。
    """
    alias: dict[str, str] = {}
    for name in names:
        alias[name.lower() if ignore_case else name] = name

    def _rule(ctx: EventContext) -> bool:
        event = ctx.message_event
        if event is None:
            return False
        text = event.plain_text.strip()
        if not text:
            return False
        for prefix in prefixes if prefixes is not None else ctx.bot.config.bot.command_prefixes:
            if not text.startswith(prefix):
                continue
            body = text[len(prefix):].lstrip()
            head, _, rest = body.partition(" ")
            key = head.lower() if ignore_case else head
            if key in alias:
                ctx.state["command"] = alias[key]
                ctx.state["args"] = rest.strip()
                return True
        return False

    return _rule


def starts_with(*prefixes: str, ignore_case: bool = False) -> Rule:
    """消息纯文本以任一前缀开头（不看命令前缀配置）。"""

    def _rule(ctx: EventContext) -> bool:
        event = ctx.message_event
        if event is None:
            return False
        text = event.plain_text.strip()
        if ignore_case:
            text = text.lower()
            return any(text.startswith(p.lower()) for p in prefixes)
        return any(text.startswith(p) for p in prefixes)

    return _rule


def regex(pattern: str, flags: int = 0) -> Rule:
    """正则搜索消息纯文本，命中后 Match 对象写入 ctx.state["match"]。"""
    compiled = re.compile(pattern, flags)

    def _rule(ctx: EventContext) -> bool:
        event = ctx.message_event
        if event is None:
            return False
        match = compiled.search(event.plain_text)
        if match is None:
            return False
        ctx.state["match"] = match
        return True

    return _rule
