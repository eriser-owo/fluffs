"""你的关键词规则：命中关键词后自动回复或执行功能函数。

两种写法（这个文件在导入时就会注册，改完用 /reload keywords_rules 或重启即可生效）：

1）固定文本自动回复 —— 往 KEYWORD_REPLIES 里加一行
2）执行功能函数 —— 用 ``@on_keyword(...)`` 装饰你的 async 函数

匹配参数（``auto_reply`` / ``on_keyword`` 的关键字参数）：

| 参数 | 可选值 | 默认 |
| --- | --- | --- |
| ``match`` | ``contains`` 出现即命中 / ``exact`` 整条相等 / ``prefix`` 以此开头 | ``contains`` |
| ``scope`` | ``group`` 仅群聊 / ``private`` 仅私聊 / ``all`` | ``group`` |
| ``at_sender`` | 自动回复时是否 @ 发送者 | ``False`` |
| ``priority`` | 越小越先匹配 | ``0`` |
| ``stop`` | 命中后是否不再匹配后面的规则（True = if/elif/else） | ``True`` |
| ``ignore_case`` | 是否忽略大小写 | ``True`` |

命中后在函数里可以拿到：``ctx.message_event``（``nickname`` / ``role_cn`` / ``plain_text`` /
``user_id`` / ``group_id``）、``ctx.bot.api.*``。异常不用自己兜，框架会记日志。
"""

from __future__ import annotations

import logging

from fluffs.config import get_active_config
from fluffs.core import EventContext
from meowers.modules.kw_reply import REGISTRY, auto_reply, on_keyword

logger = logging.getLogger(__name__)

_cfg = get_active_config()
_prefixes = _cfg.bot.command_prefixes if _cfg else []
command_prefix = (_prefixes or ["//"])[0]

__plugin_meta__ = {
    "name": "keywords_rules",
    "description": "kw规则插件",
    "usage": "支持单条自动回复或者说执行自定义函数",
    "version": "0.2.0",
}
KEYWORD_REPLIES: dict[str, str] = {
    "疯狂星期四": "V我50",
    "木合买的秘密": "是我老婆",
    "喵威尔斯,打招呼。": "你们好喵",
}

for _word, _reply in KEYWORD_REPLIES.items():
    auto_reply(_word, _reply, match = "exact")

#示例：关键词/whoami，机器人回复成员/群主/管理员
@on_keyword(f"{command_prefix}whoami", match="exact")
async def whoami(ctx: EventContext) -> None:
    event = ctx.message_event
    if event is None:
        return
    await ctx.reply(f"{event.nickname}（{event.role_cn}）", at_sender=True)


@on_keyword(f"{command_prefix}say", match="prefix", at_sender=True)
async def say(ctx: EventContext) -> None:

    text = ctx.text[len(command_prefix + "say"):].strip()
    await ctx.reply(text or f"用法：{command_prefix}say <内容>")


# @on_keyword("草猫", match="exact", at_sender=True)
# async def ro(ctx: EventContext) -> None:
#     event = ctx.message_event
#     if event is None:
#         return
#     await ctx.reply("成功草猫了", at_sender=False)



def setup(bot) -> None:
    def teardown(_bot) -> None:
        removed = REGISTRY.clear_source(__name__)
        logger.debug("把本文件登记的 %d 条关键词规则擦掉啦~", removed)

    bot.on_teardown(teardown)
    logger.info("关键词规则装好 %d 条啦喵", len(REGISTRY))
