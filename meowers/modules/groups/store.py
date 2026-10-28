"""群数据层的 SQLite 存储：groups+ members
写路径都在这里；读路径在 query.py
两张表以group_id关联
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

DB_FILENAME = "groups.db"

_CREATE_GROUPS = """
CREATE TABLE IF NOT EXISTS groups (
  group_id         INTEGER PRIMARY KEY,
  group_name       TEXT NOT NULL DEFAULT '',
  member_count     INTEGER NOT NULL DEFAULT 0,
  max_member_count INTEGER NOT NULL DEFAULT 0,
  updated_at       INTEGER NOT NULL
);
"""

_CREATE_MEMBERS = """
CREATE TABLE IF NOT EXISTS members (
  group_id     INTEGER NOT NULL,
  user_id      INTEGER NOT NULL,
  nickname     TEXT NOT NULL DEFAULT '',
  card         TEXT NOT NULL DEFAULT '',
  role         TEXT NOT NULL DEFAULT 'member',
  join_time    INTEGER NOT NULL DEFAULT 0,
  last_seen    INTEGER NOT NULL DEFAULT 0,
  status       TEXT NOT NULL DEFAULT 'active',
  left_time    INTEGER NOT NULL DEFAULT 0,
  leave_reason TEXT NOT NULL DEFAULT '',
  updated_at   INTEGER NOT NULL,
  PRIMARY KEY (group_id, user_id)
);
"""

_CREATE_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_members_group_status ON members(group_id, status);",
)


@dataclass(slots=True)
class Group:
    group_id: int
    group_name: str
    member_count: int
    max_member_count: int
    updated_at: int


@dataclass(slots=True)
class Member:
    group_id: int
    user_id: int
    nickname: str
    card: str
    role: str
    join_time: int
    last_seen: int
    status: str
    left_time: int
    leave_reason: str
    updated_at: int

    @property
    def display_name(self) -> str:
        """群内显示名：群名片优先，其次昵称，最后 QQ 号"""
        return self.card or self.nickname or str(self.user_id)

    @property
    def role_cn(self) -> str:
        return {"owner": "群主", "admin": "管理员", "member": "成员"}.get(self.role, "未知")


class GroupStore:
    """群注册表 + 群员名册的写入入口（唯一连接，写操作后 commit）"""

    def __init__(self, db_dir: Path | str = Path("data/groups"), base_dir: Path | None = None) -> None:
        self.dir = Path(db_dir)
        if not self.dir.is_absolute() and base_dir is not None:
            self.dir = base_dir / self.dir
        self.db_path = self.dir / DB_FILENAME
        self._db: aiosqlite.Connection | None = None
        self._closed = False
        self.disabled = False

    async def start(self) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.disabled = True
            logger.error("群数据目录用不了喵，本次先关掉: %s（%s）", self.dir, exc)
            return
        try:
            self._db = await aiosqlite.connect(self.db_path)
            try:
                await self._db.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                logger.debug("开启 WAL 失败喵，继续用默认模式~")
            await self._db.execute(_CREATE_GROUPS)
            await self._db.execute(_CREATE_MEMBERS)
            for sql in _CREATE_INDEX:
                await self._db.execute(sql)
            await self._db.commit()
        except Exception as exc:
            self.disabled = True
            logger.error("群数据库打不开喵，本次先关掉: %s（%s）", self.db_path, exc)
            if self._db is not None:
                await self._db.close()
                self._db = None
            return
        logger.info("群数据层就位啦喵 数据库=%s", self.db_path)

    async def close(self) -> None:
        self._closed = True
        if self._db is not None:
            try:
                await self._db.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            except Exception:
                logger.debug("WAL checkpoint 没跑成喵，不影响关闭~")
            try:
                await self._db.close()
            except Exception:
                logger.exception("关闭群数据库时出错了喵:")
            self._db = None

    # 群
    async def upsert_groups(self, groups: list[dict]) -> int:
        """把群列表写进注册表，返回写入条数"""
        if self._db is None:
            return 0
        now = int(time.time())
        rows = [
            (
                int(g.get("group_id", 0)),
                str(g.get("group_name") or ""),
                int(g.get("member_count") or 0),
                int(g.get("max_member_count") or 0),
                now,
            )
            for g in groups
            if int(g.get("group_id", 0)) > 0
        ]
        if not rows:
            return 0
        await self._db.executemany(
            "INSERT INTO groups(group_id, group_name, member_count, max_member_count, updated_at) "
            "VALUES(?,?,?,?,?) "
            "ON CONFLICT(group_id) DO UPDATE SET "
            "group_name=excluded.group_name, member_count=excluded.member_count, "
            "max_member_count=excluded.max_member_count, updated_at=excluded.updated_at",
            rows,
        )
        await self._db.commit()
        return len(rows)

    # 成员
    async def sync_members(self, group_id: int, members: list[dict]) -> int:
        """把一个群的全量成员写进名册，并把本次不在列表里的 active 成员标 left。

        返回新增 / 更新条数。入群时间已存在就保留原值，避免每次重同步把它刷新掉。
        """
        if self._db is None:
            return 0
        now = int(time.time())
        rows = []
        seen: set[int] = set()
        for m in members:
            uid = int(m.get("user_id", 0))
            if uid <= 0:
                continue
            seen.add(uid)
            rows.append(
                (
                    group_id,
                    uid,
                    str(m.get("nickname") or ""),
                    str(m.get("card") or ""),
                    str(m.get("role") or "member"),
                    int(m.get("join_time") or 0),
                    now,
                )
            )
        await self._db.executemany(
            "INSERT INTO members(group_id, user_id, nickname, card, role, join_time, updated_at, status) "
            "VALUES(?,?,?,?,?,?,?,'active') "
            "ON CONFLICT(group_id, user_id) DO UPDATE SET "
            "nickname=excluded.nickname, card=excluded.card, role=excluded.role, "
            "join_time=CASE WHEN members.join_time=0 THEN excluded.join_time ELSE members.join_time END, "
            "updated_at=excluded.updated_at, status='active', left_time=0, leave_reason=''",
            rows,
        )
        if seen:
            placeholders = ",".join("?" * len(seen))
            await self._db.execute(
                f"UPDATE members SET status='left', left_time=?, updated_at=? "
                f"WHERE group_id=? AND status='active' AND user_id NOT IN ({placeholders})",
                (now, now, group_id, *seen),
            )
        await self._db.commit()
        return len(rows)

    async def upsert_member(
        self,
        group_id: int,
        user_id: int,
        *,
        nickname: str = "",
        card: str = "",
        role: str = "member",
        join_time: int = 0,
    ) -> None:
        """入群/资料更新时 upsert 一名成员为 active（增量用）。"""
        if self._db is None:
            return
        now = int(time.time())
        await self._db.execute(
            "INSERT INTO members(group_id, user_id, nickname, card, role, join_time, updated_at, status) "
            "VALUES(?,?,?,?,?,?,?,'active') "
            "ON CONFLICT(group_id, user_id) DO UPDATE SET "
            "nickname=excluded.nickname, card=excluded.card, role=excluded.role, "
            "join_time=CASE WHEN members.join_time=0 THEN excluded.join_time ELSE members.join_time END, "
            "updated_at=excluded.updated_at, status='active', left_time=0, leave_reason=''",
            (group_id, user_id, nickname, card, role, join_time, now),
        )
        await self._db.commit()

    async def mark_left(self, group_id: int, user_id: int, reason: str = "") -> None:
        if self._db is None:
            return
        now = int(time.time())
        await self._db.execute(
            "UPDATE members SET status='left', left_time=?, leave_reason=?, updated_at=? "
            "WHERE group_id=? AND user_id=?",
            (now, reason, now, group_id, user_id),
        )
        await self._db.commit()

    async def update_card(self, group_id: int, user_id: int, card: str) -> None:
        if self._db is None:
            return
        await self._db.execute(
            "UPDATE members SET card=?, updated_at=? WHERE group_id=? AND user_id=?",
            (card, int(time.time()), group_id, user_id),
        )
        await self._db.commit()

    async def update_role(self, group_id: int, user_id: int, role: str) -> None:
        if self._db is None:
            return
        await self._db.execute(
            "UPDATE members SET role=?, updated_at=? WHERE group_id=? AND user_id=?",
            (role, int(time.time()), group_id, user_id),
        )
        await self._db.commit()

    async def touch_seen(self, group_id: int, user_id: int) -> None:
        """更新最近发言时间（仅 active 成员）。调用方应自行节流。"""
        if self._db is None:
            return
        now = int(time.time())
        await self._db.execute(
            "UPDATE members SET last_seen=?, updated_at=? "
            "WHERE group_id=? AND user_id=? AND status='active'",
            (now, now, group_id, user_id),
        )
        await self._db.commit()

    # 观测
    def status_line(self) -> str:
        if self.disabled:
            return "已降级（目录/数据库不可用）"
        return f"数据库 {self.db_path}"


__all__ = ["DB_FILENAME", "Group", "GroupStore", "Member"]
