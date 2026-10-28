"""群数据层只读查询
每调用独立开连接，只读已落盘数据；
store 里尚未提交的极少数更新看不到，属正常。
    from meowers.modules.groups import list_members, random_member, resolve_name
    picked = await random_member(group_id, count=1)   # 单群抽人
    name   = await resolve_name(group_id, user_id)     # QQ 号 -> 群名片优先的显示名
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite

from ...config import APP_ROOT
from .store import DB_FILENAME, Group, Member

_GROUPS_COLS = ("group_id", "group_name", "member_count", "max_member_count", "updated_at")
_MEMBER_COLS = (
    "group_id", "user_id", "nickname", "card", "role",
    "join_time", "last_seen", "status", "left_time", "leave_reason", "updated_at",
)
# 群主/管理员排前面，再按入群时间、QQ 号稳定排序
_MEMBER_ORDER = (
    "ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, "
    "join_time, user_id"
)


def resolve_db_path(db_dir: Path | str | None = None, base_dir: Path | None = None) -> Path:
    base = Path(db_dir) if db_dir is not None else Path("data/groups")
    if not base.is_absolute():
        base = (base_dir or APP_ROOT) / base
    return base / DB_FILENAME


def _row_to_group(row: sqlite3.Row) -> Group:
    return Group(
        group_id=int(row["group_id"]),
        group_name=str(row["group_name"]),
        member_count=int(row["member_count"]),
        max_member_count=int(row["max_member_count"]),
        updated_at=int(row["updated_at"]),
    )


def _row_to_member(row: sqlite3.Row) -> Member:
    return Member(
        group_id=int(row["group_id"]),
        user_id=int(row["user_id"]),
        nickname=str(row["nickname"]),
        card=str(row["card"]),
        role=str(row["role"]),
        join_time=int(row["join_time"]),
        last_seen=int(row["last_seen"]),
        status=str(row["status"]),
        left_time=int(row["left_time"]),
        leave_reason=str(row["leave_reason"]),
        updated_at=int(row["updated_at"]),
    )


async def list_groups(db_path: Path | str | None = None) -> list[Group]:
    """所有已同步的群。"""
    path = Path(db_path) if db_path is not None else resolve_db_path()
    if not path.is_file():
        return []
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = await conn.execute(
            f"SELECT {', '.join(_GROUPS_COLS)} FROM groups ORDER BY group_id"
        )
        rows = await cursor.fetchall()
        await cursor.close()
    return [_row_to_group(r) for r in rows]


async def get_group(group_id: int, db_path: Path | str | None = None) -> Group | None:
    path = Path(db_path) if db_path is not None else resolve_db_path()
    if not path.is_file():
        return None
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = await conn.execute(
            f"SELECT {', '.join(_GROUPS_COLS)} FROM groups WHERE group_id=?", (int(group_id),)
        )
        row = await cursor.fetchone()
        await cursor.close()
    return _row_to_group(row) if row else None


async def list_members(group_id: int, status: str = "active", db_path: Path | str | None = None) -> list[Member]:
    path = Path(db_path) if db_path is not None else resolve_db_path()
    if not path.is_file():
        return []
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = await conn.execute(
            f"SELECT {', '.join(_MEMBER_COLS)} FROM members "
            f"WHERE group_id=? AND status=? {_MEMBER_ORDER}",
            (int(group_id), status),
        )
        rows = await cursor.fetchall()
        await cursor.close()
    return [_row_to_member(r) for r in rows]


async def get_member(group_id: int, user_id: int, db_path: Path | str | None = None) -> Member | None:
    path = Path(db_path) if db_path is not None else resolve_db_path()
    if not path.is_file():
        return None
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = await conn.execute(
            f"SELECT {', '.join(_MEMBER_COLS)} FROM members WHERE group_id=? AND user_id=?",
            (int(group_id), int(user_id)),
        )
        row = await cursor.fetchone()
        await cursor.close()
    return _row_to_member(row) if row else None


async def count_members(group_id: int, status: str = "active", db_path: Path | str | None = None) -> int:
    path = Path(db_path) if db_path is not None else resolve_db_path()
    if not path.is_file():
        return 0
    async with aiosqlite.connect(path) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM members WHERE group_id=? AND status=?",
            (int(group_id), status),
        )
        row = await cursor.fetchone()
        await cursor.close()
    return int(row[0]) if row else 0


async def left_members(group_id: int, db_path: Path | str | None = None) -> list[Member]:
    return await list_members(group_id, status="left", db_path=db_path)


async def recent_active(group_id: int, limit: int = 5, db_path: Path | str | None = None) -> list[Member]:
    """最近发言的 active 成员（按 last_seen 倒序）。"""
    path = Path(db_path) if db_path is not None else resolve_db_path()
    if not path.is_file():
        return []
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = await conn.execute(
            f"SELECT {', '.join(_MEMBER_COLS)} FROM members "
            "WHERE group_id=? AND status='active' AND last_seen>0 "
            "ORDER BY last_seen DESC LIMIT ?",
            (int(group_id), int(limit)),
        )
        rows = await cursor.fetchall()
        await cursor.close()
    return [_row_to_member(r) for r in rows]


async def random_member(
    group_id: int,
    count: int = 1,
    exclude: tuple[int, ...] | list[int] = (),
    status: str = "active",
    db_path: Path | str | None = None,
) -> list[Member]:
    """从某个群里随机抽人
    exclude传要排除的 QQ 号（如机器人自己、已抽过的人）
    """
    path = Path(db_path) if db_path is not None else resolve_db_path()
    if not path.is_file():
        return []
    exclude_ids = [int(u) for u in exclude]
    sql = f"SELECT {', '.join(_MEMBER_COLS)} FROM members WHERE group_id=? AND status=?"
    params: list = [int(group_id), status]
    if exclude_ids:
        sql += f" AND user_id NOT IN ({','.join('?' * len(exclude_ids))})"
        params.extend(exclude_ids)
    sql += " ORDER BY RANDOM() LIMIT ?"
    params.append(max(1, int(count)))

    async with aiosqlite.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
        await cursor.close()
    return [_row_to_member(r) for r in rows]


async def resolve_name(group_id: int, user_id: int, db_path: Path | str | None = None) -> str:
    """QQ 号 -> 群内显示名（群名片优先）；没找到就回退 QQ 号。"""
    member = await get_member(group_id, user_id, db_path=db_path)
    return member.display_name if member else str(user_id)


__all__ = [
    "count_members",
    "get_group",
    "get_member",
    "left_members",
    "list_groups",
    "list_members",
    "random_member",
    "recent_active",
    "resolve_db_path",
    "resolve_name",
]
