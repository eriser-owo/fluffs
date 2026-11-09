from __future__ import annotations

import asyncio
import logging

from fluffs.core import EventContext, rules

from ...config import APP_ROOT
from .memory import MEMORY_SIZE, SUMMARY_BATCH, ConversationMemory
from .prompt import build_user_input
from .providers import ChatMessage, LLMError, create_provider
from .vision import build_vision_message, image_data_url, resolve_reference

logger = logging.getLogger(__name__)

__plugin_meta__ = {
    "name": "llm_chat",
    "description": "大模型对话：@机器人 触发（带每群共享记忆/总结），带图时自动识图",
    "usage": "@机器人 <内容>、@机器人 + 图片、//清空",
    "version": "0.6.0",
}

_HINT = "尚未配置大模型"

_SUMMARIZE_SYSTEM = (
    "你是群聊记忆的摘要助手。把输入压缩成一段简洁的中文摘要，"
    "保留：参与者昵称、主要话题、达成的结论或约定、重要事实。"
    "只输出摘要正文，不要寒暄、不要列表标题。"
)


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


def _format_turns(turns) -> str:
    return "\n".join(
        f"{'用户' if t.role == 'user' else '助手'}: {t.content}"
        for t in turns
    )


async def setup(bot) -> None:
    provider = create_provider(bot.config.llm)
    memory = ConversationMemory(base_dir=APP_ROOT)
    await memory.start()
    bot.services["llm_chat"] = _LLMStatus(provider, bot.config.llm)
    bot.services["llm_provider"] = provider
    bot.services["llm_memory"] = memory
    busy: set[str] = set()
    _summarizing: set[str] = set()
    _bg_tasks: set[asyncio.Task] = set()

    def _spawn(coro, name: str) -> None:
        task = asyncio.create_task(coro, name=name)
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)

    async def _summarize(previous: str, turns) -> str:
        old = f"之前的摘要：\n{previous}\n\n" if previous else ""
        conversation = _format_turns(turns)
        messages = [
            ChatMessage("system", _SUMMARIZE_SYSTEM),
            ChatMessage("user", f"{old}新增对话：\n{conversation}\n\n请给出合并后的摘要："),
        ]
        return (await provider.complete(messages, temperature=0.3)).strip()

    async def _maybe_summarize(key: str) -> None:
        if provider is None or key in _summarizing:
            return
        _summarizing.add(key)
        try:
            latest = await memory.latest_id(key)
            prev = await memory.get_summary(key)
            upto = prev[1] if prev else 0
            target = latest - MEMORY_SIZE
            if target - upto < SUMMARY_BATCH:
                return
            turns = await memory.summarize_candidates(key, upto, target)
            if not turns:
                return
            new_summary = await _summarize(prev[0] if prev else "", turns)
            await memory.set_summary(key, new_summary, target)
            logger.info("记忆总结好啦喵 %s 已总结到 id=%d", key, target)
        except Exception:
            logger.exception("记忆总结失败喵（不影响对话）")
        finally:
            _summarizing.discard(key)

    async def _do_vision(ctx: EventContext, text: str, quoted_text: str, seg: dict) -> None:
        data_url = await image_data_url(bot.api, seg)
        if not data_url:
            await ctx.send("这张图我拿不到喵，可能格式不支持")
            return
        messages = [
            ChatMessage("system", bot.config.llm.system_prompt),
            build_vision_message(text, data_url, quoted_text),
        ]
        try:
            answer = await provider.complete(
                messages,
                model=bot.config.llm.vision_model,
                thinking={"type": "enabled"},
                reasoning_effort="high",
            )
        except LLMError as exc:
            logger.warning("识图失败喵: %s", exc)
            await ctx.send("识图翻车啦喵，稍后再试")
            return
        except Exception:
            logger.exception("识图冒出个异常喵")
            await ctx.send("识图出了点问题，已记录日志")
            return
        await ctx.send(answer)

    async def _do_text(ctx: EventContext, key: str, event, text: str, quoted_text: str) -> None:
        try:
            summary = await memory.get_summary(key)
            history = await memory.history(key)
            system_text = bot.config.llm.system_prompt
            if summary:
                system_text = f"{system_text}\n\n【以下是之前对话的摘要】\n{summary[0]}"
            messages = [
                ChatMessage("system", system_text),
                *history,
                ChatMessage("user", build_user_input(event, quoted_text)),
            ]
            answer = await provider.complete(messages)
        except LLMError as exc:
            logger.warning("呜，模型没理我喵: %s", exc)
            await ctx.send("模型调用失败了，稍后再试(已生成日志)")
            return
        except Exception:
            logger.exception("llm_chat 模块里冒了个异常喵")
            await ctx.send("出了点问题，已记录到日志")
            return

        try:
            stored = text or "(回复了一条消息)"
            await memory.append(key, "user", f"{event.nickname}: {stored}")
            await memory.append(key, "assistant", answer)
        except Exception:
            logger.exception("写记忆失败喵（不影响回复）")

        await ctx.send(answer)
        _spawn(_maybe_summarize(key), "llm-summarize")

    @bot.on_message(rules.to_me(allow_private=bot.config.llm.allow_private), priority=20)
    async def on_mention(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None:
            return
        text = event.plain_text.strip()
        prefixes = tuple(bot.config.bot.command_prefixes)
        if prefixes and text.startswith(prefixes):
            return

        if provider is None:
            await ctx.send(_HINT)
            return

        key = f"group:{event.group_id}" if event.is_group else f"user:{event.user_id}"
        if key in busy:
            await ctx.send("上一句还在生成，稍等一下~")
            return

        busy.add(key)
        try:
            # 拿到要识别的图 + 被回复消息的文本
            seg, quoted_text = await resolve_reference(event, bot.api)

            # 有图且配了识图模型 → 识图
            if seg is not None and bot.config.llm.vision_model:
                await _do_vision(ctx, text, quoted_text, seg)
                return

            # 否则走文字（含被回复的文本；没配识图模型也照常文字回复）
            if not text and not quoted_text:
                await ctx.send("你 @ 了我，但没说话呢")
                return
            await _do_text(ctx, key, event, text, quoted_text)
        finally:
            busy.discard(key)

    @bot.on_command("清空")
    async def clear_memory(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None:
            return
        if event.is_group:
            if not rules.from_superuser()(ctx):
                await ctx.send("只有超级用户能清空群记忆喵")
                return
            key = f"group:{event.group_id}"
        else:
            key = f"user:{event.user_id}"
        await memory.clear(key)
        await ctx.send("记忆已清空喵")

    async def teardown(_bot) -> None:
        bot.services.pop("llm_chat", None)
        bot.services.pop("llm_memory", None)
        for task in list(_bg_tasks):
            task.cancel()
        if _bg_tasks:
            await asyncio.gather(*_bg_tasks, return_exceptions=True)
        if provider is not None:
            await provider.aclose()
        await memory.close()
        logger.info("llm_chat 模块收工啦喵，资源都放回原位~")

    bot.on_teardown(teardown)
