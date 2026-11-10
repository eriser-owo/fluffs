"""cat_checkin 插件：猫猫签到（签到 / 补签 / 签到榜）。"""

from __future__ import annotations

from .main import setup

__plugin_meta__ = {
    "name": "cat_checkin",
    "description": "猫猫签到：发「签到」打卡、发「补签 {DD}」补签、发「签到榜」看本月榜单",
    "usage": "签到、补签 {DD}、签到榜",
    "version": "0.5.0",
    "author": "eriser-owo",
}

__all__ = ["setup"]
