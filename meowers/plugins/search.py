from __future__ import annotations

import asyncio
import logging

from ddgs import DDGS

from fluffs.config import get_active_config
from fluffs.core import EventContext
from fluffs.napcat import message as msg

logger = logging.getLogger(__name__)

_cfg = get_active_config()
_prefixes = _cfg.bot.command_prefixes if _cfg else []
command_prefix = (_prefixes or ["//"])[0]

__plugin_meta__ = {
    "name": "search",
    "description": "简单的网页搜索喵。",
    "usage": f"{command_prefix}搜索/search  {{关键词}}",
    "version": "0.3.0",
    "author": "Eriser",
}


def _sync_search(query: str, max_results: int = 3) -> list[dict]:
    """DDGS 搜索。safesearch="on" 以防止滥用。"""
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, region="cn-zh", safesearch="on", max_results=max_results):
            results.append({
                "title": r.get("title", ""),
                "href": r.get("href", ""),
            })
    return results


def setup(bot) -> None:
    @bot.on_command("搜索", "search")
    async def on_search(ctx: EventContext) -> None:
        query = ctx.state.get("args", "").strip()
        if not query:
            await ctx.reply(f"用法：{command_prefix}搜索 关键词")
            return

        await ctx.reply(f"喵正在搜「{query}」，等一下下...")

        try:
            results = await asyncio.to_thread(_sync_search, query, 3)

            if not results:
                await ctx.reply("呜，什么也没搜到喵。")
                return

            parts = []
            for idx, res in enumerate(results, 1):
                title = res["title"][:30]
                href = res["href"]
                parts.append(f"{idx}. {title}\n{href}\n")

            reply_text = f"搜到了喵！关于「{query}」的结果：\n\n" + "\n".join(parts)

            await ctx.reply(msg.build(reply_text.strip()))

        except Exception as e:
            logger.exception("搜索翻车啦喵: %s", e)
            await ctx.reply("搜索翻车啦喵！")
