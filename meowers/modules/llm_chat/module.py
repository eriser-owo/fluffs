from __future__ import annotations

import logging

from fluffs.core import EventContext, rules
from .prompt import build_user_input
from .providers import ChatMessage, LLMError, create_provider

logger = logging.getLogger(__name__)

__plugin_meta__ = {
    "name": "llm_chat",
    "description": "大模型对话：群聊里 @机器人 即触发（私聊需开 allow_private），单条输入",
    "usage": "@机器人 <内容>",
    "version": "0.3.0",
}

_HINT = "尚未配置大模型"


class _LLMStatus:


    def __init__(self, provider, config) -> None:
        self._provider = provider
        self._config = config

    def status_line(self) -> str:
        if not self._config.enabled:
            return "未启用"
        if self._provider is None:
            return f"{self._config.provider} 未就绪"
        return f"{self._config.provider}/{self._config.model}"


def setup(bot) -> None:
    provider = create_provider(bot.config.llm)
    bot.services["llm_chat"] = _LLMStatus(provider, bot.config.llm)
    bot.services["llm_provider"] = provider
    busy: set[str] = set()


    @bot.on_message(rules.to_me(allow_private=bot.config.llm.allow_private), priority=20)
    async def on_mention(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None:
            return
        text = event.plain_text.strip()
        if not text:
            await ctx.reply("你 @ 了我，但没说话呢")
            return
        prefixes = tuple(bot.config.bot.command_prefixes)
        if prefixes and text.startswith(prefixes):
            return

        if provider is None:
            await ctx.reply(_HINT)
            return

        key = f"group:{event.group_id}" if event.is_group else f"user:{event.user_id}"
        if key in busy:
            await ctx.reply("上一句还在生成，稍等一下~")
            return

        busy.add(key)
        try:
            messages = [
                ChatMessage("system", bot.config.llm.system_prompt),
                ChatMessage("user", build_user_input(event)),
            ]
            answer = await provider.complete(messages)
        except LLMError as exc:
            logger.warning("呜，模型没理我喵: %s", exc)
            await ctx.reply("模型调用失败了，稍后再试(已生成日志)")
            return
        except Exception:
            logger.exception("llm_chat 模块里冒了个异常喵")
            await ctx.reply("出了点问题，已记录到日志")
            return
        finally:
            busy.discard(key)

        await ctx.reply(answer)

    async def teardown(_bot) -> None:
        bot.services.pop("llm_chat", None)
        if provider is not None:
            await provider.aclose()
        logger.info("llm_chat 模块收工啦喵，资源都放回原位~")

    bot.on_teardown(teardown)
