"""关键词检测模块。

职责边界（三件事都在这个目录里，不再散落到别处）：
    匹配    registry.py —— 匹配方式（contains / exact / prefix）、命中判定
    分支    registry.py —— 一条规则 = 一个分支，动作可以是"固定回复"或"功能函数"
    执行    module.py   —— 注册一个 message 处理器，按顺序尝试分支，命中即执行

规则从哪里来：你自己的 ``meowers/plugins/keywords_rules.py`` 里调用
``auto_reply()`` / ``on_keyword()`` 注册；本模块负责把它们接到事件流上。

用户侧用法：

    from meowers.modules.kw_reply import auto_reply, on_keyword

    auto_reply("/test", "OK")                       # 命中即自动回复
    auto_reply("签到", "签到成功", scope="all")      # 私聊也生效
    auto_reply(["/t", "测试"], "OK")                # 多个关键词共用一句回复

    @on_keyword("/查分", match="prefix")            # 命中即执行功能函数
    async def query_score(ctx): ...
"""

from __future__ import annotations

from .module import setup
from .registry import (
    MATCH_MODES,
    REGISTRY,
    SCOPES,
    KeywordBranch,
    KeywordRegistry,
    auto_reply,
    on_keyword,
)

__all__ = [
    "MATCH_MODES",
    "REGISTRY",
    "SCOPES",
    "KeywordBranch",
    "KeywordRegistry",
    "auto_reply",
    "on_keyword",
    "setup",
]
