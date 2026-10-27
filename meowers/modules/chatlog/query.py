"""chatlog.db 只读查询工具
返回recorder.ChatRecord
注意：只能读到已flush进SQLite的数据，recorder内存缓冲里还没落盘的那部分看不到。

from meowers.modules.chatlog import query_messages, count_messages, resolve_db_path

# 按群/人/关键词/时间段
rows = await query_messages(group_id=123456, keyword="草", limit=20)
# 计数
n    = await count_messages(user_id=10001)
# data/chatlog/chatlog.db
path = resolve_db_path()

"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

import aiosqlite

from ...config import APP_ROOT, ChatLogConfig
from .recorder import ChatRecord

logger = logging.getLogger(__name__)

_DB_FILENAME = "chatlog.db"
_COLUMNS = ("time", "group_id", "user_id", "nickname", "role", "message_id", "text")


def resolve_db_path(config: ChatLogConfig | None = None, base_dir: Path | None = None) -> Path:
    """按 ``config.chatlog.dir`` 算出数据库路径（默认 ``data/chatlog/chatlog.db``）。"""
    cfg = config or ChatLogConfig()
    base = Path(cfg.dir)
    if not base.is_absolute():
        base = (base_dir or APP_ROOT) / base
    return base / _DB_FILENAME


def _row_to_record(row: sqlite3.Row) -> ChatRecord:
    return ChatRecord(
        time=int(row["time"]),
        group_id=int(row["group_id"]),
        user_id=int(row["user_id"]),
        nickname=str(row["nickname"]),
        role=str(row["role"]),
        message_id=int(row["message_id"]),
        text=str(row["text"]),
    )


def _build_where(
    *,
    group_id: int | None,
    user_id: int | None,
    keyword: str | None,
    start: int | None,
    end: int | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if group_id is not None:
        clauses.append("group_id = ?")
        params.append(int(group_id))
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(int(user_id))
    if keyword:
        clauses.append("text LIKE ?")
        params.append(f"%{keyword}%")
    if start is not None:
        clauses.append("time >= ?")
        params.append(int(start))
    if end is not None:
        clauses.append("time <= ?")
        params.append(int(end))
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


async def query_messages(
    *,
    db_path: Path | str | None = None,
    group_id: int | None = None,
    user_id: int | None = None,
    keyword: str | None = None,
    start: int | None = None,
    end: int | None = None,
    limit: int = 100,
    offset: int = 0,
    order: str = "DESC",
) -> list[ChatRecord]:
    """查聊天记录，返回ChatRecord列表（默认按时间倒序）。
        rows = await query_messages(group_id=123456, keyword="草", limit=20)
    """
    path = Path(db_path) if db_path is not None else resolve_db_path()
    if not path.is_file():
        raise FileNotFoundError(f"聊天记录数据库不存在: {path}")

    where, params = _build_where(
        group_id=group_id, user_id=user_id, keyword=keyword, start=start, end=end
    )
    order_by = "DESC" if str(order).upper() != "ASC" else "ASC"
    sql = (
        f"SELECT {', '.join(_COLUMNS)} FROM chat_log{where} "
        f"ORDER BY time {order_by}, id {order_by} LIMIT ? OFFSET ?"
    )
    params.extend([int(limit), int(offset)])

    async with aiosqlite.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        await cursor.close()
    return [_row_to_record(r) for r in rows]


async def count_messages(
    *,
    db_path: Path | str | None = None,
    group_id: int | None = None,
    user_id: int | None = None,
    keyword: str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> int:
    """统计符合条件的记录条数。数据库不存在时返回 0。"""
    path = Path(db_path) if db_path is not None else resolve_db_path()
    if not path.is_file():
        return 0

    where, params = _build_where(
        group_id=group_id, user_id=user_id, keyword=keyword, start=start, end=end
    )
    sql = f"SELECT COUNT(*) FROM chat_log{where}"

    async with aiosqlite.connect(path) as conn:
        cursor = await conn.execute(sql, params)
        row = await cursor.fetchone()
        await cursor.close()
    return int(row[0]) if row else 0


__all__ = ["count_messages", "query_messages", "resolve_db_path"]
