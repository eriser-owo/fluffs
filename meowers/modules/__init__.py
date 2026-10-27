"""MeowersBot 的业务模块层：一个功能 = 一个目录，自己带注册、逻辑与配置读取。

| 模块 | 功能 | 触发 |
| --- | --- | --- |
| ``kw_reply`` | 关键词检测 → 自动回复 / 功能函数 | 群消息命中关键词（可配私聊）|
| ``llm_chat`` | 大模型对话（含 providers） | 仅被 @ 时，单条输入 |
| ``chatlog`` | 聊天记录归档（缓冲 + 落盘） | 群消息 |

模块就是一个插件包：``meowers.modules`` 被扫描时，只会加载**子包本身**
（读它的 ``__init__.py``），不会递归进包内部的实现文件。
所以模块内部可以自由拆分文件（registry / module / recorder …）而不会被当成插件加载。

新增模块：在 ``modules/`` 下建包，写 ``__init__.py`` 暴露 ``setup(bot)``，
需要的话再加 ``teardown(bot)``；随后到 ``config.toml`` 的
``bot.plugin_modules`` 里确认 ``meowers.modules`` 在扫描列表中即可。

依赖方向：``meowers.modules`` → ``fluffs``（框架）与本 App 的 ``config``；
框架反过来不认识本 App，任何时候都不要让 fluffs 里 import meowers。
"""

from __future__ import annotations

__all__: list[str] = []
