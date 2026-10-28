"""群数据模块装配：同步触发 + notice 增量 + 命令 + 挂服务。

保活策略（三层）：
1. lifecycle 元事件（enable/connect）→ 后台全量同步；
2. notice 事件 → 入群 / 退群 / 改名片 / 改职位的增量更新；
3. 周期任务（RESYNC_INTERVAL）→ 补改昵称这类没有 notice 的变化。
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from fluffs.config import get_active_config
from fluffs.core import EventContext, rules
from fluffs.napcat import MetaEvent, NoticeEvent

from ...config import APP_ROOT
from . import query as q
from .store import GroupStore

logger = logging.getLogger(__name__)

RESYNC_INTERVAL = 6 * 3600  # 秒：6 小时
SEEN_COOLDOWN = 60.0       # 秒：同一成员 last_seen 的最小写间隔

_cfg = get_active_config()
_prefixes = _cfg.bot.command_prefixes if _cfg else []
command_prefix = (_prefixes or ["//"])[0]

__plugin_meta__ = {
    "name": "groups",
    "description": "群数据层：群注册表 + 群员名册（data/groups/groups.db），供抽人/按群查询等复用",
    "usage": f"{command_prefix}成员 <QQ/@>|left|刷新、{command_prefix}群、{command_prefix}抽人 [人数]",
    "version": "0.1.0",
}

_ROLE_CN = {"owner": "群主", "admin": "管理员", "member": "成员"}


def _fmt_time(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "未知"


def _parse_qq(ctx: EventContext, arg: str) -> int:
    """优先取 @ 段里的 QQ 号，其次把参数当纯数字 QQ 号。"""
    event = ctx.message_event
    if event is not None:
        ids = [i for i in event.at_user_ids if i != -1]
        if ids:
            return ids[0]
    return int(arg) if arg.isdigit() else 0


def _is_lifecycle_enable(ctx: EventContext) -> bool:
    event = ctx.event
    return (
        isinstance(event, MetaEvent)
        and event.meta_event_type == "lifecycle"
        and event.sub_type in ("enable", "connect")
    )


def _is_member_notice(ctx: EventContext) -> bool:
    event = ctx.event
    return isinstance(event, NoticeEvent) and event.notice_type in (
        "group_increase", "group_decrease", "group_card", "group_admin"
    )


async def setup(bot) -> None:
    store = GroupStore(base_dir=APP_ROOT)
    await store.start()
    bot.services["groups"] = store

    _seen: dict[tuple[int, int], float] = {}
    _bg_tasks: set[asyncio.Task] = set()

    def _spawn(coro, name: str) -> None:
        task = asyncio.create_task(coro, name=name)
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)

    async def full_sync() -> None:
        """全量同步：群注册表 + 每群名册。失败只记日志、不中断。"""
        if store.disabled or not bot.ready:
            return
        try:
            groups = await bot.api.get_group_list()
        except Exception:
            logger.exception("拉群列表失败喵")
            return
        await store.upsert_groups(groups)
        for group in groups:
            gid = int(group.get("group_id", 0))
            if gid <= 0:
                continue
            try:
                members = await bot.api.get_group_member_list(gid)
                await store.sync_members(gid, members)
                logger.info("群 %s 名册同步好啦喵 %d 人", gid, len(members))
            except Exception:
                logger.exception("拉群 %s 成员列表失败喵", gid)
        logger.info("群数据全量同步完成喵 共 %d 个群", len(groups))

    async def resync_loop() -> None:
        while True:
            await asyncio.sleep(RESYNC_INTERVAL)
            await full_sync()

    _spawn(resync_loop(), "groups-resync")

    @bot.on_meta(_is_lifecycle_enable)
    async def _on_lifecycle(_ctx: EventContext) -> None:
        _spawn(full_sync(), "groups-full-sync")

    @bot.on_notice(_is_member_notice)
    async def _on_member_notice(ctx: EventContext) -> None:
        event = ctx.event
        if not isinstance(event, NoticeEvent) or not event.group_id:
            return
        try:
            if event.notice_type == "group_increase":
                info: dict = {}
                try:
                    info = await bot.api.get_group_member_info(event.group_id, event.user_id)
                except Exception:
                    pass
                await store.upsert_member(
                    event.group_id,
                    event.user_id,
                    nickname=str(info.get("nickname") or ""),
                    card=str(info.get("card") or ""),
                    role=str(info.get("role") or "member"),
                    join_time=int(info.get("join_time") or event.time or 0),
                )
                logger.info("群里来新成员啦喵 %s 入群 %s", event.user_id, event.group_id)
            elif event.notice_type == "group_decrease":
                await store.mark_left(event.group_id, event.user_id, event.sub_type or "")
            elif event.notice_type == "group_card":
                card = str(event.raw.get("card_new") or event.raw.get("card") or "")
                await store.update_card(event.group_id, event.user_id, card)
            elif event.notice_type == "group_admin":
                await store.update_role(
                    event.group_id, event.user_id, "admin" if event.sub_type == "set" else "member"
                )
        except Exception:
            logger.exception("群名册增量更新绊了一下喵: %s", event.notice_type)

    @bot.on_message(rules.group_only, priority=90, passive=True)
    async def _on_group_message(ctx: EventContext) -> None:
        event = ctx.message_event
        if event is None:
            return
        key = (event.group_id, event.user_id)
        now = time.monotonic()
        if now - _seen.get(key, 0.0) < SEEN_COOLDOWN:
            return
        _seen[key] = now
        try:
            await store.touch_seen(event.group_id, event.user_id)
        except Exception:
            logger.debug("更新 last_seen 失败喵: %s/%s", event.group_id, event.user_id)

    # 命令
    @bot.on_command("成员", "名单")
    async def members_cmd(ctx: EventContext) -> None:
        event = ctx.message_event
        gid = event.group_id if event else 0
        if not gid:
            await ctx.reply("这个命令要在群里用喵")
            return

        arg = ctx.args.strip()

        if arg == "刷新":
            if not rules.from_superuser()(ctx):
                await ctx.reply("只有超级用户能刷新喵")
                return
            await ctx.reply("正在重拉当前群名单...")
            try:
                members = await bot.api.get_group_member_list(gid)
                n = await store.sync_members(gid, members)
                await ctx.reply(f"刷新完成喵，本群名册 {n} 人")
            except Exception as exc:
                logger.exception("重拉群名单失败喵")
                await ctx.reply(f"重拉失败: {exc}")
            return

        if arg == "left":
            members = await q.left_members(gid)
            if not members:
                await ctx.reply("还没记录到退群成员喵")
                return
            lines = [f"已退群（{len(members)} 人）："]
            for m in members[:30]:
                lines.append(f"· {m.display_name}（{m.user_id}）")
            await ctx.reply("\n".join(lines))
            return

        if arg:
            uid = _parse_qq(ctx, arg)
            if not uid:
                await ctx.reply(f"用法：{command_prefix}成员 <QQ号/@某人|left|刷新>")
                return
            m = await q.get_member(gid, uid)
            if m is None:
                await ctx.reply("名册里没找到这个人喵（可能还没同步）")
                return
            status_txt = "在群" if m.status == "active" else f"已退群（{m.leave_reason or '原因未知'}）"
            lines = [
                f"{m.display_name}（{m.user_id}）",
                f"职位: {m.role_cn}",
                f"状态: {status_txt}",
                f"入群: {_fmt_time(m.join_time)}",
            ]
            if m.status == "active" and m.last_seen:
                lines.append(f"最近发言: {_fmt_time(m.last_seen)}")
            await ctx.reply("\n".join(lines))
            return

        active = await q.list_members(gid, "active")
        left = await q.count_members(gid, "left")
        owner = sum(1 for m in active if m.role == "owner")
        admin = sum(1 for m in active if m.role == "admin")
        lines = [
            f"群成员统计（{len(active)} 人，已退 {left} 人）",
            f"· 群主 {owner} / 管理员 {admin} / 成员 {len(active) - owner - admin}",
        ]
        recent = await q.recent_active(gid, 3)
        if recent:
            lines.append("最近活跃：")
            for m in recent:
                lines.append(f"· {m.display_name}（{_fmt_time(m.last_seen)}）")
        await ctx.reply("\n".join(lines))

    @bot.on_command("群",rule = rules.from_superuser())
    async def groups_cmd(ctx: EventContext) -> None:
        groups = await q.list_groups()
        if not groups:
            await ctx.reply("还没同步到任何群喵（连上 NapCat 后会自动同步）")
            return
        lines = ["我所在的群："]
        for g in groups:
            lines.append(f"· {g.group_name or g.group_id}（{g.group_id}）· {g.member_count} 人")
        await ctx.reply("\n".join(lines))

    @bot.on_command("抽人")
    async def pick_cmd(ctx: EventContext) -> None:
        event = ctx.message_event
        gid = event.group_id if event else 0
        if not gid:
            await ctx.reply("这个命令要在群里用喵")
            return
        count = 1
        arg = ctx.args.strip()
        if arg.isdigit():
            count = max(1, min(10, int(arg)))
        exclude = [bot.api.self_id] if bot.api.self_id else []
        try:
            picked = await q.random_member(gid, count=count, exclude=exclude)
        except Exception:
            logger.exception("抽人失败喵")
            await ctx.reply("抽人翻车啦喵")
            return
        if not picked:
            await ctx.reply("名册里没有可抽的成员喵（可能还没同步）")
            return
        names = "、".join(m.display_name for m in picked)
        await ctx.reply(f"抽中：{names}", at_sender=True)

    # --- 卸载 -------------------------------------------------------------
    async def teardown(_bot) -> None:
        bot.services.pop("groups", None)
        for task in list(_bg_tasks):
            task.cancel()
        if _bg_tasks:
            await asyncio.gather(*_bg_tasks, return_exceptions=True)
        await store.close()

    bot.on_teardown(teardown)
