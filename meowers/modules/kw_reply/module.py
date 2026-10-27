"""关键词模块的装配：把注册表接到事件流上。

执行语义（对应"if/else 分支"）：
1. 只处理消息事件，取纯文本；
2. 按 ``priority`` 顺序逐条尝试分支：
   - 先看生效范围（群聊 / 私聊 / 全部）；
   - 再看关键词是否命中；
   - 命中就执行动作（自动回复 or 你的功能函数）；
   - 分支的 ``stop=True``（默认）表示命中即结束 → 等价 if/elif/else；
     设成 ``False`` 则继续匹配后面的分支 → 等价多个独立 if。
"""

from __future__ import annotations

import logging

from fluffs.core import EventContext, rules
from .registry import REGISTRY, KeywordBranch

logger = logging.getLogger(__name__)

__plugin_meta__ = {
    "name": "kw_reply",
    "description": "关键词检测：命中关键词后自动回复或执行功能函数（规则写在 plugins/keywords_rules.py）",
    "usage": "在 plugins/keywords_rules.py 里用 auto_reply() / @on_keyword() 添加",
    "version": "0.2.0",
}

#: 关键词分支的执行优先级（数值越小越先跑；命令类插件默认也是 10，同级按注册顺序）
KEYWORD_PRIORITY = 10


def _scope_ok(branch: KeywordBranch, ctx: EventContext) -> bool:
    return rules.scope(branch.scope)(ctx)


def setup(bot) -> None:
    # 把注册表挂到 bot.services，/status 与其它模块可以读实时条数
    bot.services["kw_reply"] = REGISTRY

    @bot.on_message(rules.message_only, priority=KEYWORD_PRIORITY)
    async def keywords_dispatch(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None:
            return
        text = event.plain_text.strip()
        if not text:
            return

        for branch in REGISTRY.branches:
            if not _scope_ok(branch, ctx) or not branch.matches(text):
                continue
            try:
                await branch.run(ctx)
            except Exception:
                logger.exception("关键词分支绊了一跤喵: %s", "/".join(branch.words))
            if branch.stop:
                break

    # 规则文件在 plugins 包之后加载，这里只报当前数量
    logger.debug("关键词小词典准备好啦喵 现有 %d 条规则~", len(REGISTRY))
