"""byr 插件：//byr 问题 —— 让 AI 搜索北邮生存指南文档并总结回答。"""

from __future__ import annotations

import asyncio
import logging
import re

from fluffs.config import get_active_config
from fluffs.core import EventContext

from meowers.config import APP_ROOT
from meowers.modules.llm_chat.providers import ChatMessage

logger = logging.getLogger(__name__)

_cfg = get_active_config()
_prefixes = _cfg.bot.command_prefixes if _cfg else []
command_prefix = (_prefixes or ["//"])[0]

DOCS_DIR = APP_ROOT / "data" / "bupt-survival-guide" / "src" / "content" / "docs"

__plugin_meta__ = {
    "name": "byr",
    "description": f"{command_prefix}byr 问题 —— AI 搜索北邮生存指南文档并总结回答",
    "usage": f"{command_prefix}byr <问题>",
    "version": "0.1.0",
    "author": "eriser-owo",
}

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "在北邮生存指南的本地文档里搜索相关内容，返回匹配的文件名和内容片段",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "要搜索的关键词或问题"}
                },
                "required": ["query"],
            },
        },
    }
]

_SYSTEM_EXTRA = (
    "你可以调用 search_docs 工具搜索「北邮生存指南」的本地文档。"
    "回答用户关于北邮（校园、食堂、宿舍、学习、生活等）的问题时，"
    "先搜索文档、再基于文档内容总结回答；查不到就说查不到，不要编造。"
)

def _search_docs(query: str, limit: int = 5) -> str:
    """在 DOCS_DIR 下全文搜索 md 文件，返回格式化文本。"""
    if not DOCS_DIR.is_dir():
        return "文档目录不存在，无法搜索。"

    tokens = [t for t in re.split(r"\s+", query.strip()) if t]
    scored = []
    for p in DOCS_DIR.rglob("*.md"):
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        low = content.lower()
        q = query.strip().lower()
        score = 0.0
        if q and q in low:
            score += 6
        for t in tokens:
            if t.lower() in low:
                score += 3
        if score == 0:
            cjk = "".join(ch for ch in query if "\u4e00" <= ch <= "\u9fff")
            if cjk:
                score = sum(1 for ch in set(cjk) if ch in low) / max(len(set(cjk)), 1)
        if score > 0:
            scored.append((score, p, content))

    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return "没搜到相关文档。"

    parts = []
    for _score, p, content in scored[:limit]:
        rel = p.relative_to(DOCS_DIR)
        parts.append(f"【{rel}】\n{content[:600]}")
    return "\n\n".join(parts)


async def _tool_executor(name: str, args: dict) -> str:
    if name != "search_docs":
        return f"未知工具 {name}"
    query = str(args.get("query") or "")
    if not query:
        return "查询为空"
    return await asyncio.to_thread(_search_docs, query)


def setup(bot) -> None:
    @bot.on_command("byr")
    async def on_byr(ctx: EventContext) -> None:
        question = ctx.args.strip()
        if not question:
            await ctx.send(f"用法：{command_prefix}byr <问题>")
            return

        provider = bot.services.get("llm_provider")
        if provider is None:
            await ctx.send("还没配置大模型喵")
            return

        messages = [
            ChatMessage("system", bot.config.llm.system_prompt + "\n\n" + _SYSTEM_EXTRA),
            ChatMessage("user", question),
        ]

        await ctx.send("喵正在翻bupt生存指南...")
        try:
            answer = await provider.complete_tools(messages, _TOOLS, _tool_executor)
        except Exception as exc:
            logger.exception("搜索失败喵")
            await ctx.send(f"搜索翻车啦喵：{exc}")
            return
        await ctx.send(answer)
