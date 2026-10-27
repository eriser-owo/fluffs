"""MeowersBot 应用配置：在 Fluffs 框架配置之上追加本 App 的业务配置段。

配置文件是 ``config/config.toml``，环境变量（含 ``.env``）统一用 ``FLUFFS_`` 前缀覆盖它。

    [connection] / [bot] / [log]   框架段，schema 见 fluffs.config
    [llm]                          大模型对话（modules/llm_chat）
    [chatlog]                      聊天记录归档（modules/chatlog）

加载流程复用框架原语：``read_toml`` -> ``build`` -> ``apply_env``。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fluffs.config import (
    BotConfig,
    ConnectionConfig,
    FluffsConfig,
    LogConfig,
    apply_env,
    build,
    env_bool,
    env_int_list,
    load_dotenv,
    mask,
    read_toml,
)

logger = logging.getLogger(__name__)

#: 应用根目录（本文件在 meowers/ 下，往上一层就是项目根）
APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = APP_ROOT / "config" / "config.toml"
DEFAULT_ENV_PATH = APP_ROOT / ".env"
ENV_PREFIX = "FLUFFS_"


@dataclass(slots=True)
class LLMConfig:
    """大模型对话配置（modules/llm_chat）。"""

    enabled: bool = False
    provider: str = "openai_compat"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    system_prompt: str = (
        "本模块是 QQ 群聊机器人。输入会给出这条消息的发送者昵称、职位（成员/管理员/群主）和消息原文，"
        "只针对这一条消息作答。回复用纯文本、不要 Markdown、尽量简短。"
        "你的人设：喵威尔斯bot，可爱，猫娘，北京邮电大学男娘"
    )
    temperature: float = 0.7
    max_tokens: int = 1024
    timeout: float = 60.0
    # 群聊一律要求 @ 机器人；私聊是否也允许对话（规范为「仅 @」，故默认关闭）
    allow_private: bool = False


@dataclass(slots=True)
class ChatLogConfig:
    """聊天记录归档配置（modules/chatlog）。"""

    enabled: bool = True
    # all: 记录所有群消息（完整聊天档案）
    # mention: 只记录 @ 了机器人的消息
    scope: str = "all"
    dir: str = "data/chatlog"  # 相对项目根目录
    flush_interval: float = 60.0  # 定时落盘间隔（秒），<=0 表示只按条数触发
    max_buffer: int = 200  # 缓冲达到该条数立即落盘


@dataclass(slots=True)
class AppBotConfig(BotConfig):
    """App 侧的 Bot 配置：默认扫描「框架内置 + 本 App 的模块与插件」。"""

    plugin_modules: list[str] = field(
        default_factory=lambda: ["fluffs.builtin", "meowers.modules", "meowers.plugins"]
    )


@dataclass(slots=True)
class AppConfig(FluffsConfig):
    """应用总配置 = 框架段（connection/bot/log）+ 应用段（llm/chatlog）。"""

    bot: AppBotConfig = field(default_factory=AppBotConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    chatlog: ChatLogConfig = field(default_factory=ChatLogConfig)

    def summary(self) -> dict[str, Any]:
        """启动日志用的摘要：框架段 + 应用段（敏感字段打码）。"""
        data = super().summary()
        data["llm"] = {
            "enabled": self.llm.enabled,
            "provider": self.llm.provider,
            "model": self.llm.model,
            "base_url": self.llm.base_url,
            "api_key": mask(self.llm.api_key),
        }
        data["chatlog"] = {
            "enabled": self.chatlog.enabled,
            "scope": self.chatlog.scope,
            "dir": self.chatlog.dir,
            "flush_interval": self.chatlog.flush_interval,
            "max_buffer": self.chatlog.max_buffer,
        }
        return data


def _env_mapping(config: AppConfig) -> dict[str, tuple[Any, str, Any]]:
    """环境变量 -> 配置字段。前缀由 App 决定（框架不规定）。"""
    return {
        # 框架段
        f"{ENV_PREFIX}CONNECTION_MODE": (config.connection, "mode", str),
        f"{ENV_PREFIX}HOST": (config.connection, "host", str),
        f"{ENV_PREFIX}PORT": (config.connection, "port", int),
        f"{ENV_PREFIX}PATH": (config.connection, "path", str),
        f"{ENV_PREFIX}TOKEN": (config.connection, "token", str),
        f"{ENV_PREFIX}FORWARD_URL": (config.connection, "forward_url", str),
        f"{ENV_PREFIX}SELF_ID": (config.bot, "self_id", int),
        f"{ENV_PREFIX}SUPERUSERS": (config.bot, "superusers", env_int_list),
        f"{ENV_PREFIX}IGNORE_SELF": (config.bot, "ignore_self", env_bool),
        f"{ENV_PREFIX}LOG_LEVEL": (config.log, "level", str),
        # 应用段
        f"{ENV_PREFIX}LLM_ENABLED": (config.llm, "enabled", env_bool),
        f"{ENV_PREFIX}LLM_PROVIDER": (config.llm, "provider", str),
        f"{ENV_PREFIX}LLM_BASE_URL": (config.llm, "base_url", str),
        f"{ENV_PREFIX}LLM_API_KEY": (config.llm, "api_key", str),
        f"{ENV_PREFIX}LLM_MODEL": (config.llm, "model", str),
        f"{ENV_PREFIX}LLM_ALLOW_PRIVATE": (config.llm, "allow_private", env_bool),
        f"{ENV_PREFIX}CHATLOG_ENABLED": (config.chatlog, "enabled", env_bool),
        f"{ENV_PREFIX}CHATLOG_SCOPE": (config.chatlog, "scope", str),
        f"{ENV_PREFIX}CHATLOG_DIR": (config.chatlog, "dir", str),
        f"{ENV_PREFIX}CHATLOG_FLUSH_INTERVAL": (config.chatlog, "flush_interval", float),
        f"{ENV_PREFIX}CHATLOG_MAX_BUFFER": (config.chatlog, "max_buffer", int),
    }


def load_config(path: str | Path | None = None) -> AppConfig:
    """读取配置：``.env`` + ``config/config.toml`` + 环境变量覆盖。"""
    load_dotenv(DEFAULT_ENV_PATH)

    candidate = Path(path or os.environ.get(f"{ENV_PREFIX}CONFIG") or DEFAULT_CONFIG_PATH)
    if not candidate.is_absolute():
        candidate = APP_ROOT / candidate

    raw, resolved = read_toml(candidate)
    config = build(AppConfig, raw)
    apply_env(config, _env_mapping(config))
    config.source = str(resolved) if resolved.is_file() else ""
    return config


__all__ = [
    "APP_ROOT",
    "AppBotConfig",
    "AppConfig",
    "BotConfig",
    "ChatLogConfig",
    "ConnectionConfig",
    "DEFAULT_CONFIG_PATH",
    "FluffsConfig",
    "LLMConfig",
    "LogConfig",
    "load_config",
]
