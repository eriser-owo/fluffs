"""关键词注册表：收集「关键词 → 动作」的分支，并提供命中判定。

一条分支（``KeywordBranch``）就是这个模块里的一个 if：
    关键词 + 匹配方式 + 生效范围  →  命中后做的事（自动回复文本 / 功能函数）

设计要点：
- **幂等**：分支以 ``(关键词, 匹配方式, 范围, 来源模块)`` 为键，重复注册会覆盖旧值，
  所以热重载 / 重复 import 不会产生重复回复；
- **来源可清**：``clear_source(模块名)`` 用于热重载时清掉该文件注册过的全部分支
  （包括你已从文件里删掉的那些），保证"文件即事实"。
"""

from __future__ import annotations

import inspect
import logging
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fluffs.core import EventContext

logger = logging.getLogger(__name__)

MATCH_MODES = ("contains", "exact", "prefix")
SCOPES = ("group", "private", "all")

# 动作：固定回复用字符串，功能函数用 async def action(ctx) -> None
Action = Callable[["EventContext"], Any]


def _caller_module(depth: int = 2) -> str:
    """取调用方的模块名，作为分支来源（用于幂等与按来源清理）。"""
    try:
        return str(sys._getframe(depth).f_globals.get("__name__", ""))
    except (AttributeError, ValueError):  # pragma: no cover - 极端情况下退化
        return ""


@dataclass(slots=True)
class KeywordBranch:
    """一个关键词分支。"""

    words: tuple[str, ...]
    action: str | Action
    match: str = "contains"
    scope: str = "group"
    ignore_case: bool = True
    at_sender: bool = False
    stop: bool = True  # 命中后是否终止后续分支：True = if/elif/else，False = 多个 if 都执行
    priority: int = 0  # 越小越先匹配
    source: str = ""
    _targets: tuple[str, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        if not self.words:
            raise ValueError("关键词不能为空")
        if self.match not in MATCH_MODES:
            raise ValueError(f"未知的匹配方式 {self.match!r}，可选: {', '.join(MATCH_MODES)}")
        if self.scope not in SCOPES:
            raise ValueError(f"未知的生效范围 {self.scope!r}，可选: {', '.join(SCOPES)}")
        self._targets = tuple(w.lower() for w in self.words) if self.ignore_case else tuple(self.words)

    @property
    def key(self) -> tuple[Any, ...]:
        """幂等键。"""
        return (self.words, self.match, self.scope, self.source)

    @property
    def is_reply(self) -> bool:
        return isinstance(self.action, str)

    def matches(self, text: str) -> bool:
        """这条分支是否命中给定文本。"""
        if not text:
            return False
        haystack = text.lower() if self.ignore_case else text
        if self.match == "exact":
            return haystack in self._targets
        if self.match == "prefix":
            return any(haystack.startswith(word) for word in self._targets)
        return any(word in haystack for word in self._targets)

    async def run(self, ctx: "EventContext") -> None:
        """执行分支动作。"""
        if isinstance(self.action, str):
            await ctx.reply(self.action, at_sender=self.at_sender)
            return
        result = self.action(ctx)
        if inspect.isawaitable(result):
            await result


class KeywordRegistry:
    """按注册顺序保存所有分支。"""

    def __init__(self) -> None:
        self._branches: dict[tuple[Any, ...], KeywordBranch] = {}

    def add(
        self,
        *words: str,
        action: str | Action,
        match: str = "contains",
        scope: str = "group",
        ignore_case: bool = True,
        at_sender: bool = False,
        stop: bool = True,
        priority: int = 0,
        source: str = "",
    ) -> KeywordBranch:
        branch = KeywordBranch(
            words=tuple(words),
            action=action,
            match=match,
            scope=scope,
            ignore_case=ignore_case,
            at_sender=at_sender,
            stop=stop,
            priority=priority,
            source=source or _caller_module(2),
        )
        if branch.key in self._branches:
            logger.info("关键词分支被新版覆盖掉啦喵 %s（%s/%s）", "/".join(branch.words), branch.match, branch.scope)
        self._branches[branch.key] = branch
        logger.debug("记下一条关键词分支喵 %s -> %s", "/".join(branch.words), "自动回复" if branch.is_reply else "功能函数")
        return branch

    @property
    def branches(self) -> list[KeywordBranch]:
        """按 priority、注册顺序返回全部分支。"""
        return sorted(self._branches.values(), key=lambda b: b.priority)

    def clear_source(self, source: str) -> int:
        """清掉某个模块注册过的分支（热重载用）。返回清理条数。"""
        keys = [key for key, branch in self._branches.items() if branch.source == source]
        for key in keys:
            del self._branches[key]
        if keys:
            logger.debug("把 %s 之前登记的 %d 条分支擦掉啦喵~", source, len(keys))
        return len(keys)

    def clear(self) -> None:
        self._branches.clear()

    def __len__(self) -> int:
        return len(self._branches)

    def status_line(self) -> str:
        """框架 /status 直接显示这一行。"""
        reply_branches = sum(1 for branch in self._branches.values() if branch.is_reply)
        return f"{len(self._branches)} 条规则（{reply_branches} 条自动回复 / {len(self._branches) - reply_branches} 条功能函数）"


#: 全局注册表：插件里的规则注册到这里，由 module.py 统一执行
REGISTRY = KeywordRegistry()


def auto_reply(
    words: str | Iterable[str],
    reply: str,
    *,
    match: str = "contains",
    scope: str = "group",
    ignore_case: bool = True,
    at_sender: bool = False,
    stop: bool = True,
    priority: int = 0,
) -> KeywordBranch:
    """注册"命中即自动回复固定文本"的分支。

        auto_reply("/test", "OK")                     # 一个关键词
        auto_reply(["/test", "测试"], "OK")            # 多个别名共用一句回复
        auto_reply("签到", "签到成功", scope="all")     # 私聊也生效

    :param match: contains（出现即命中，默认）/ exact（整条相等）/ prefix（以此开头）
    :param scope: group（默认仅群聊）/ private（仅私聊）/ all
    :param at_sender: 回复时是否 @ 发送者（默认否）
    :param stop: 命中后是否不再匹配后续分支（默认是）
    """
    targets = (words,) if isinstance(words, str) else tuple(words)
    return REGISTRY.add(
        *targets,
        action=reply,
        match=match,
        scope=scope,
        ignore_case=ignore_case,
        at_sender=at_sender,
        stop=stop,
        priority=priority,
        source=_caller_module(2),
    )


def on_keyword(
    *words: str,
    match: str = "contains",
    scope: str = "group",
    ignore_case: bool = True,
    at_sender: bool = False,
    stop: bool = True,
    priority: int = 0,
) -> Callable[[Action], Action]:
    """装饰器：命中关键词后执行被装饰的 async 函数。

        @on_keyword("/查分", match="prefix")
        async def query_score(ctx): ...
    """
    source = _caller_module(2)

    def decorator(func: Action) -> Action:
        REGISTRY.add(
            *words,
            action=func,
            match=match,
            scope=scope,
            ignore_case=ignore_case,
            at_sender=at_sender,
            stop=stop,
            priority=priority,
            source=source,
        )
        return func

    return decorator


__all__ = [
    "MATCH_MODES",
    "REGISTRY",
    "SCOPES",
    "Action",
    "KeywordBranch",
    "KeywordRegistry",
    "auto_reply",
    "on_keyword",
]
