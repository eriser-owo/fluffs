"""
聊天记录存储：内存缓冲 + 批量落盘（SQLite 版）。
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import aiosqlite

from ...config import APP_ROOT, ChatLogConfig
from fluffs.napcat import MessageEvent

logger = logging.getLogger(__name__)

_DB_FILENAME = "chatlog.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS chat_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    time        INTEGER NOT NULL,
    group_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    nickname    TEXT    NOT NULL,
    role        TEXT    NOT NULL,
    message_id  INTEGER NOT NULL,
    text        TEXT    NOT NULL
);
"""

_CREATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_chat_log_time ON chat_log(time);",
    "CREATE INDEX IF NOT EXISTS idx_chat_log_group_time ON chat_log(group_id, time);",
    "CREATE INDEX IF NOT EXISTS idx_chat_log_user_time ON chat_log(user_id, time);",
)

_INSERT_SQL = """
INSERT INTO chat_log (time, group_id, user_id, nickname, role, message_id, text)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


@dataclass(slots=True)
class ChatRecord:

    time: int
    group_id: int
    user_id: int
    nickname: str
    role: str
    message_id: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_row(self) -> tuple[Any, ...]:
        """给 executemany 用的行元组，顺序与 _INSERT_SQL 的占位符一致。"""
        return (
            self.time,
            self.group_id,
            self.user_id,
            self.nickname,
            self.role,
            self.message_id,
            self.text,
        )

    @classmethod
    def from_event(cls, event: MessageEvent) -> "ChatRecord":
        return cls(
            time=event.time or int(time.time()),
            group_id=event.group_id,
            user_id=event.user_id,
            nickname=event.nickname,
            role=event.role_cn,
            message_id=event.message_id,
            text=event.plain_text.strip() or event.raw_message.strip(),
        )


class ChatLogRecorder:

    def __init__(self, config: ChatLogConfig, base_dir: Path | None = None) -> None:
        self.config = config
        self.base_dir = Path(config.dir)
        if not self.base_dir.is_absolute():
            self.base_dir = (base_dir or APP_ROOT) / self.base_dir
        self.db_path = self.base_dir / _DB_FILENAME
        self.written = 0
        self.dropped = 0
        self.failures = 0
        self.disabled = False
        self._buffer: list[ChatRecord] = []
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._closed = False
        self._db: aiosqlite.Connection | None = None

    async def start(self) -> None:
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.disabled = True
            logger.error("聊天记录的小本本目录用不了喵，本次归档先关掉: %s（%s）", self.base_dir, exc)
            return

        try:
            self._db = await aiosqlite.connect(self.db_path)
            # WAL 模式对「边写边读」更友好；开不起来也不影响基本功能
            try:
                await self._db.execute("PRAGMA journal_mode=WAL;")
            except sqlite3.Error:
                logger.debug("开启 WAL 模式失败喵，继续用默认模式~")
            await self._db.execute(_CREATE_TABLE_SQL)
            for sql in _CREATE_INDEX_SQL:
                await self._db.execute(sql)
            await self._db.commit()
        except (OSError, sqlite3.Error) as exc:
            self.disabled = True
            logger.error("聊天记录数据库打不开喵，本次归档先关掉: %s（%s）", self.db_path, exc)
            if self._db is not None:
                await self._db.close()
                self._db = None
            return

        if self.config.flush_interval > 0:
            self._task = asyncio.create_task(self._flush_loop(), name="chatlog-flush")
        logger.info(
            "聊天记录准备好开始记啦喵 数据库=%s 范围=%s 间隔=%.0fs 缓冲上限=%d",
            self.db_path,
            self.config.scope,
            self.config.flush_interval,
            self.config.max_buffer,
        )

    async def aclose(self) -> None:
        """停止定时任务、把剩余缓冲刷盘，并关闭数据库连接。"""
        self._closed = True
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        flushed = await self.flush()
        if self._db is not None:
            try:
                await self._db.close()
            except sqlite3.Error:
                logger.exception("关闭聊天记录数据库时出错了喵:")
            self._db = None
        logger.info("聊天记录归档收工喵，累计写下 %d 条，最后补了 %d 条~", self.written, flushed)

    # --- 写入 -------------------------------------------------------------
    async def record(self, event: MessageEvent) -> None:
        """记一条消息；缓冲满时顺带刷盘。"""
        if self._closed or self.disabled:
            return
        self._buffer.append(ChatRecord.from_event(event))
        if len(self._buffer) >= max(self.config.max_buffer, 1):
            await self.flush()

    async def flush(self) -> int:
        """把缓冲批量写入 SQLite，返回本次成功写入条数。"""
        async with self._lock:
            if not self._buffer:
                return 0
            if self._db is None:
                # 连接没建立（start 失败或已关闭），直接丢弃避免内存无限增长
                dropped = len(self._buffer)
                self._buffer.clear()
                self.dropped += dropped
                return 0

            batch, self._buffer = self._buffer, []
            rows = [rec.to_row() for rec in batch]
            try:
                await self._db.executemany(_INSERT_SQL, rows)
                await self._db.commit()
            except asyncio.CancelledError:
                # 被取消时尽量回滚，避免留下半截事务
                try:
                    await self._db.rollback()
                except sqlite3.Error:
                    logger.debug("回滚也失败啦喵~")
                self._buffer[:0] = batch
                raise
            except sqlite3.Error:
                # 持续失败（磁盘满/数据库损坏/被锁死）时不能每个周期都打完整堆栈
                self.failures += 1
                if self.failures == 1:
                    logger.exception("小本本一时写不进去喵，%d 条先塞回缓冲，稍后再试~", len(batch))
                elif self.failures % 10 == 0:
                    logger.error(
                        "小本本已经连续写失败 %d 次喵（累计丢了 %d 条），这次先退回 %d 条~",
                        self.failures,
                        self.dropped,
                        len(batch),
                    )
                else:
                    logger.debug("小本本还是没写成喵（第 %d 次叹气）~", self.failures)
                try:
                    await self._db.rollback()
                except sqlite3.Error:
                    logger.debug("回滚也失败啦喵~")
                self._buffer[:0] = batch
                self._trim_overflow()
                return 0

            self.failures = 0
            self.written += len(batch)
            logger.debug("小本本写好啦喵 %d 条 -> %s", len(batch), self.db_path)
            return len(batch)

    def _trim_overflow(self) -> None:
        """落盘一直失败时，丢掉最旧的记录，避免内存无限增长。"""
        hard_limit = max(self.config.max_buffer, 1) * 10
        if len(self._buffer) > hard_limit:
            overflow = len(self._buffer) - hard_limit
            del self._buffer[:overflow]
            self.dropped += overflow
            logger.error("缓冲涨破硬上限啦喵，丢掉最旧的 %d 条（累计丢 %d 条）", overflow, self.dropped)

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.flush_interval)
            try:
                await self.flush()
            except Exception:
                logger.exception("定时写小本本失败了喵:")

    # --- 观测 -------------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        """给 /status 用的统计。"""
        return {
            "dir": str(self.base_dir),
            "db": str(self.db_path),
            "scope": self.config.scope,
            "buffered": len(self._buffer),
            "written": self.written,
            "dropped": self.dropped,
            "failures": self.failures,
            "disabled": self.disabled,
        }

    def status_line(self) -> str:
        """框架 /status 直接显示这一行。"""
        if self.disabled:
            return "已降级（目录/数据库不可用）"
        return f"缓冲 {len(self._buffer)} 条 / 已落盘 {self.written} 条（范围 {self.config.scope}）"


__all__ = ["ChatLogRecorder", "ChatRecord"]