"""Fluffs 框架配置

框架只认这三段（App 可以在其上追加自己的段）：

    [connection]  怎么连 NapCat（协议层用）
    [bot]         Bot 通用行为：self_id / 超级用户 / 命令前缀 / 插件扫描包……
    [log]         日志级别与文件

另外提供与配置内容无关的通用原语，App 直接复用即可：
    read_toml / build / apply_env / load_dotenv / env_bool / env_int_list / mask

App 侧示例（见 meowers/config.py）：
    @dataclass(slots=True)
    class AppConfig(FluffsConfig):
        llm: LLMConfig = field(default_factory=LLMConfig)
    config = build(FluffsConfig, read_toml(path))
    apply_env(config, {"FLUFFS_LLM_API_KEY": (config.llm, "api_key", str)})
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, get_type_hints

logger = logging.getLogger(__name__)

_active_config: Any = None

@dataclass(slots=True)
class ConnectionConfig:
    """与 NapCat（OneBot 11 实现）的连接参数。"""

    mode: str = "reverse_ws"  # reverse_ws | forward_ws
    host: str = "127.0.0.1"
    port: int = 8080
    path: str = "/onebot/v11/ws"
    token: str = ""
    forward_url: str = "ws://127.0.0.1:3001"
    reconnect_interval: float = 3.0
    api_timeout: float = 30.0


@dataclass(slots=True)
class BotConfig:
    """Bot 通用行为参数（与业务无关）。"""

    self_id: int = 0
    superusers: list[int] = field(default_factory=list)
    command_prefixes: list[str] = field(default_factory=lambda: ["//"])
    # 忽略机器人自己发出的消息（NapCat 开启"上报自身消息"时会出现）：
    # 否则"关键词回复的内容里又含该关键词"会造成自触发循环
    ignore_self: bool = True
    # 依次扫描的插件包；框架默认只扫自己的内置命令，App 会覆盖成"内置 + 自己的模块与插件"
    plugin_modules: list[str] = field(default_factory=lambda: ["fluffs.builtin"])
    disabled_plugins: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LogConfig:
    level: str = "INFO"
    file: str = ""


@dataclass(slots=True)
class FluffsConfig:
    """框架配置总成；App 继承它来追加自己的配置段。"""

    connection: ConnectionConfig = field(default_factory=ConnectionConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    log: LogConfig = field(default_factory=LogConfig)
    source: str = ""  # 实际读取到的配置文件路径

    def summary(self) -> dict[str, Any]:
        """用于启动日志的安全摘要（敏感字段打码）。"""
        return {
            "config_source": self.source or "<内置默认值>",
            "connection": {
                "mode": self.connection.mode,
                "listen": f"{self.connection.host}:{self.connection.port}{self.connection.path}",
                "forward_url": self.connection.forward_url,
                "token": mask(self.connection.token),
            },
            "bot": {
                "self_id": self.bot.self_id,
                "superusers": self.bot.superusers,
                "command_prefixes": self.bot.command_prefixes,
                "ignore_self": self.bot.ignore_self,
                "plugin_modules": self.bot.plugin_modules,
            },
            "log": {"level": self.log.level, "file": self.log.file or "<控制台>"},
        }


# --- 通用原语 -------------------------------------------------------------
def set_active_config(config: Any) -> None:
    """由 loader 在加载插件前调用，把已解析的配置暴露给插件。

    插件在 import 阶段（``__plugin_meta__`` 生成时）拿不到 ``bot``，
    通过 ``get_active_config()`` 读这份配置，避免各自拼路径读文件。
    """
    global _active_config
    _active_config = config

def get_active_config() -> Any:
    """插件读当前生效的配置；未初始化时返回 ``None``（调用方自行兜底）。"""
    return _active_config

def mask(secret: str) -> str:
    """给日志用的打码。"""
    if not secret:
        return "<空>"
    return f"***{secret[-4:]}" if len(secret) > 4 else "***"


def strip_env_comment(value: str) -> str:
    """ << Obsolete! >>

   剥掉 .env 值后面的行尾注释。
   规则（按顺序判断）：
   1. ``#`` 前面是空白、或后面紧跟空白（含行尾）→ 视为注释起点
      （``60# 定时落盘秒数`` -> ``60``、``abc # 说明`` -> ``abc``）；
   2. ``#`` 前面的内容是纯数字 → 也视为注释（``200#缓冲`` -> ``200``）；
   3. 其余情况原样保留，避免误伤含 ``#`` 的密钥（``sk-abc#def`` 不变）。
   """
    for index, char in enumerate(value):
        if char != "#":
            continue
        before = value[index - 1] if index else " "
        after = value[index + 1] if index + 1 < len(value) else " "
        if before.isspace() or after.isspace():
            return value[:index].strip()
        try:
            float(value[:index].strip())  # 数字后面直接跟 # 也算注释
        except ValueError:
            continue
        return value[:index].strip()
    return value.strip()


def load_dotenv(path: str | Path) -> None:
    """把 .env 里的键值对读进 os.environ（已存在的环境变量不覆盖）。

    支持 ``KEY=值``、引号包裹（引号内原样保留）以及行尾 ``# 注释``。
    """
    env_path = Path(path)
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw_value = line.partition("=")
        key = key.strip()
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]  # 引号内的内容原样保留（可含 #）
        else:
            value = strip_env_comment(value)
        if key and key not in os.environ:
            os.environ[key] = value


def read_toml(path: str | Path) -> tuple[dict[str, Any], Path]:
    """读取 TOML 配置，返回 (内容, 实际路径)；文件不存在时返回空配置。"""
    candidate = Path(path)
    if not candidate.is_file():
        logger.warning("咦，没找到配置文件 %s，那就先用内置默认值顶着喵~", candidate)
        return {}, candidate
    with candidate.open("rb") as fh:
        return tomllib.load(fh), candidate


def build(config_type: type, raw: dict[str, Any]) -> Any:
    """按 dataclass 定义递归地把 dict 转成配置对象，忽略未知键。"""
    hints = get_type_hints(config_type)
    kwargs: dict[str, Any] = {}
    for f in fields(config_type):
        if f.name not in raw:
            continue
        value = raw[f.name]
        field_type = hints.get(f.name)
        if isinstance(field_type, type) and is_dataclass(field_type) and isinstance(value, dict):
            kwargs[f.name] = build(field_type, value)
        else:
            kwargs[f.name] = value
    return config_type(**kwargs)


def apply_env(config: Any, mapping: dict[str, tuple[Any, str, Any]]) -> None:
    """按映射用环境变量覆盖配置。

    ``mapping`` 形如 ``{"FLUFFS_TOKEN": (config.connection, "token", str)}``；
    由调用方（App）决定用哪些变量名，框架不规定前缀。
    """
    for env_name, (target, attr, caster) in mapping.items():
        value = os.environ.get(env_name)
        if value is None or value == "":
            continue
        try:
            setattr(target, attr, caster(value))
        except (TypeError, ValueError):
            logger.warning("这个环境变量 %s 的值我看不懂啦，先跳过喵 原值: %r", env_name, value)


def env_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int_list(value: str) -> list[int]:
    return [int(item) for item in value.replace(",", " ").split() if item.strip()]


__all__ = [
    "BotConfig",
    "ConnectionConfig",
    "FluffsConfig",
    "LogConfig",
    "apply_env",
    "build",
    "env_bool",
    "env_int_list",
    "get_active_config",
    "load_dotenv",
    "mask",
    "read_toml",
    "strip_env_comment",
    "set_active_config",
]
