"""你的扩展区：这个包里的每个 .py 都会被自动加载。

放什么：
    keywords_rules.py   关键词规则（命中关键词 → 自动回复 / 功能函数）
    echo.py             示例：命令插件
    poke.py             示例：通知事件（戳一戳）
    _template.py        插件模板；下划线开头不会被加载，复制它开新插件

写插件的最小形态：

    __plugin_meta__ = {"name": "my_plugin", "description": "示例", "usage": "/hello"}

    def setup(bot):                      # 同步或异步都行
        @bot.on_command("hello")
        async def hello(ctx):
            await ctx.reply("world")

    async def teardown(bot): ...         # 可选：卸载/退出时释放资源

可用入口：bot.on_command / on_message / on_notice / on_request / on_meta / on_event。
想加"关键词自动回复"请改 keywords_rules.py，不要另起一套匹配逻辑。

import 约定（体现分层）：
    from fluffs.core import EventContext, rules      # 上下文与规则
    from fluffs.napcat import MessageEvent, NoticeEvent, message   # 事件与消息段
"""

from __future__ import annotations

__all__: list[str] = []
