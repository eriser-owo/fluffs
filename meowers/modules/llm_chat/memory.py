"""LLM 对话记忆：SQLite 持久化的每群/每用户多轮历史。

原始消息永远保留（``memory`` 表）；读上下文时只取最近 ``MEMORY_SIZE`` 条，
更早的部分由 module.py 交给 LLM 总结成摘要（存 ``memory_summary`` 表），
避免上下文越滚越大。key 约定：群聊 ``group:{gid}``、私聊 ``user:{uid}``。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import aiosqlite

from ...config import APP_ROOT
from .providers import ChatMessage

logger = logging.getLogger(__name__)

DB_FILENAME = "memory.db"
MEMORY_SIZE = 12     # 读进上下文的最近原始条数
SUMMARY_BATCH = 12   # 攒够这么多条旧消息才总结一次（批量，省 LLM 调用）

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS memory (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  key        TEXT NOT NULL,
  role       TEXT NOT NULL,
  content    TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
"""
_CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_memory_key_id ON memory(key, id);"

_CREATE_SUMMARY = """
CREATE TABLE IF NOT EXISTS memory_summary (
  key        TEXT PRIMARY KEY,
  content    TEXT NOT NULL,
  upto_id    INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
"""


class ConversationMemory:
    """多轮对话记忆（SQLite，重启后仍在）。原始记录不删，旧的部分单独总结。"""

    def __init__(self, db_dir: Path | str = Path("data/llm_chat"), base_dir: Path | None = None) -> None:
        self.dir = Path(db_dir)
        if not self.dir.is_absolute() and base_dir is not None:
            self.dir = base_dir / self.dir
        self.db_path = self.dir / DB_FILENAME
        self.limit = MEMORY_SIZE
        self._db: aiosqlite.Connection | None = None
        self.disabled = False

    async def start(self) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.disabled = True
            logger.error("记忆目录用不了喵，本次先关掉: %s（%s）", self.dir, exc)
            return
        try:
            self._db = await aiosqlite.connect(self.db_path)
            try:
                await self._db.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                logger.debug("开启 WAL 失败喵，继续用默认模式~")
            await self._db.execute(_CREATE_SQL)
            await self._db.execute(_CREATE_INDEX)
            await self._db.execute(_CREATE_SUMMARY)
            await self._db.commit()
        except Exception as exc:
            self.disabled = True
            logger.error("记忆数据库打不开喵，本次先关掉: %s（%s）", self.db_path, exc)
            if self._db is not None:
                await self._db.close()
                self._db = None
            return
        logger.info("LLM 记忆就位啦喵 数据库=%s 上下文最近=%d 条", self.db_path, self.limit)

    async def close(self) -> None:
        if self._db is not None:
            try:
                await self._db.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            except Exception:
                logger.debug("WAL checkpoint 没跑成喵，不影响关闭~")
            try:
                await self._db.close()
            except Exception:
                logger.exception("关闭记忆数据库时出错了喵:")
            self._db = None

    async def history(self, key: str, limit: int | None = None) -> list[ChatMessage]:
        """按时间正序返回该 key 的最近 ``limit`` 条（默认 MEMORY_SIZE）。"""
        if self._db is None:
            return []
        n = self.limit if limit is None else int(limit)
        cur = await self._db.execute(
            "SELECT role, content FROM memory WHERE key=? ORDER BY id DESC LIMIT ?",
            (key, n),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [ChatMessage(str(role), str(content)) for role, content in reversed(rows)]

    async def append(self, key: str, role: str, content: str) -> None:
        """追加一条原始记忆（不裁剪，永久保留）。"""
        if self._db is None or not content:
            return
        await self._db.execute(
            "INSERT INTO memory(key, role, content, created_at) VALUES(?,?,?,?)",
            (key, role, content, int(time.time())),
        )
        await self._db.commit()

    async def get_summary(self, key: str) -> tuple[str, int] | None:
        """返回 (摘要内容, 已总结到的最大 id)；没有则 None。"""
        if self._db is None:
            return None
        cur = await self._db.execute(
            "SELECT content, upto_id FROM memory_summary WHERE key=?", (key,)
        )
        row = await cur.fetchone()
        await cur.close()
        return (str(row[0]), int(row[1])) if row else None

    async def latest_id(self, key: str) -> int:
        """该 key 当前最大的原始消息 id；没有则 0。"""
        if self._db is None:
            return 0
        cur = await self._db.execute(
            "SELECT COALESCE(MAX(id), 0) FROM memory WHERE key=?", (key,)
        )
        row = await cur.fetchone()
        await cur.close()
        return int(row[0]) if row else 0

    async def summarize_candidates(self, key: str, after_id: int, upto_id: int) -> list[ChatMessage]:
        """id 在 (after_id, upto_id] 之间的原始消息，按时间正序。"""
        if self._db is None:
            return []
        cur = await self._db.execute(
            "SELECT role, content FROM memory WHERE key=? AND id>? AND id<=? ORDER BY id",
            (key, after_id, upto_id),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [ChatMessage(str(role), str(content)) for role, content in rows]

    async def set_summary(self, key: str, content: str, upto_id: int) -> None:
        if self._db is None:
            return
        await self._db.execute(
            "INSERT INTO memory_summary(key, content, upto_id, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET content=excluded.content, "
            "upto_id=excluded.upto_id, updated_at=excluded.updated_at",
            (key, content, upto_id, int(time.time())),
        )
        await self._db.commit()

    async def clear(self, key: str) -> None:
        if self._db is None:
            return
        await self._db.execute("DELETE FROM memory WHERE key=?", (key,))
        await self._db.execute("DELETE FROM memory_summary WHERE key=?", (key,))
        await self._db.commit()

    def status_line(self) -> str:
        if self.disabled:
            return "已降级（目录/数据库不可用）"
        return f"数据库 {self.db_path}"


__all__ = ["ConversationMemory", "MEMORY_SIZE", "SUMMARY_BATCH"]
