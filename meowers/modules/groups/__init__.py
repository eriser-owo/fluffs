"""
data/groups/groups.db，bot.services["groups"]
    from meowers.modules.groups import random_member, resolve_name
    picked = await random_member(group_id, count=1)
    name   = await resolve_name(group_id, user_id)
"""

from __future__ import annotations

from .module import setup
from .query import (
    count_members,
    get_group,
    get_member,
    left_members,
    list_groups,
    list_members,
    random_member,
    recent_active,
    resolve_name,
)
from .store import Group, GroupStore, Member

__all__ = [
    "Group",
    "GroupStore",
    "Member",
    "count_members",
    "get_group",
    "get_member",
    "left_members",
    "list_groups",
    "list_members",
    "random_member",
    "recent_active",
    "resolve_name",
    "setup",
]
