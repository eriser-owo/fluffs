"""
config.toml 配置扫描包 导入模块 调用setup(bot)
fluffs.builtin = 框架内置管理命令
meowers.modules = App 的业务模块
meowers.plugins = 轻型扩展
__plugin_meta__ = {...}   元信息
def setup(bot): ...       同步或异步；在这里注册处理函数
async def teardown(_bot):  卸载 / 退出时释放资源
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING, Any
from ..config import set_active_config

if TYPE_CHECKING:
    from .bot import FluffsBot

logger = logging.getLogger(__name__)

# 加载插件时用它标记"当前正在注册谁的处理函数"，便于按插件卸载
_CURRENT_PLUGIN: ContextVar[str | None] = ContextVar("fluffs_plugin", default=None)


def current_plugin() -> str | None:
    """name of the plugin currently loaded (used as a tag when registering handler functions)."""
    return _CURRENT_PLUGIN.get()


def _first_line(doc: str | None) -> str:
    """used for desc"""
    if not doc:
        return ""
    for line in doc.strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


@dataclass(slots=True)
class PluginMeta:
    name: str
    module: str = ""
    description: str = ""
    usage: str = ""
    version: str = "0.1.0"
    author: str = ""
    enabled: bool = True

    @classmethod
    def of(cls, module: ModuleType) -> "PluginMeta":
        short = module.__name__.rsplit(".", 1)[-1]
        raw: dict[str, Any] = getattr(module, "__plugin_meta__", {}) or {}
        if isinstance(raw, PluginMeta):
            meta = raw
            meta.module = meta.module or module.__name__
            return meta
        return cls(
            name=str(raw.get("name") or short),
            module=module.__name__,
            description=str(raw.get("description") or _first_line(module.__doc__)),
            usage=str(raw.get("usage") or ""),
            version=str(raw.get("version") or "0.1.0"),
            author=str(raw.get("author") or ""),
            enabled=bool(raw.get("enabled", True)),
        )


class PluginManager:

    def __init__(self, bot: "FluffsBot") -> None:
        self.bot = bot
        set_active_config(bot.config)
        self.loaded: dict[str, PluginMeta] = {}
        self.modules: dict[str, ModuleType] = {}
        self._teardowns: dict[str, Callable[..., Any]] = {}

    def add_teardown(self, func: Callable[..., Any]) -> bool:
        """把 teardown 记到当前正在 setup 的插件名下（由 bot.on_teardown 调用）"""
        name = current_plugin()
        if name is None:
            return False
        self._teardowns[name] = func
        return True

    async def load_all(self, packages: list[str] | None = None) -> list[PluginMeta]:
        targets = packages if packages is not None else self.bot.config.bot.plugin_modules
        for package_name in targets:
            await self.load_package(package_name)
        logger.info("插件集合完毕喵 一共 %d 位: %s", len(self.loaded), ", ".join(self.loaded) or "无")
        return list(self.loaded.values())

    async def load_package(self, package_name: str) -> list[PluginMeta]:
        try:
            package = importlib.import_module(package_name)
        except ImportError:
            logger.exception("插件包打不开喵: %s", package_name)
            return []
        paths = getattr(package, "__path__", None)
        if paths is None:  # not package but single module
            meta = await self.load_module(package_name)
            return [meta] if meta else []

        result: list[PluginMeta] = []
        for info in pkgutil.iter_modules(paths, prefix=f"{package_name}."):
            if info.name.rsplit(".", 1)[-1].startswith("_"):
                continue  # ignore loading _
            meta = await self.load_module(info.name)
            if meta is not None:
                result.append(meta)
        return result

    async def load_module(self, module_name: str) -> PluginMeta | None:
        short = module_name.rsplit(".", 1)[-1]
        if short in self.bot.config.bot.disabled_plugins:
            logger.info("插件 %s 在配置里被禁足啦，跳过喵~", short)
            return None
        if module_name in self.modules:
            logger.debug("插件 %s 早就加载过了，不用重复喵", module_name)
            return self.loaded.get(short)

        try:
            module = importlib.import_module(module_name)
        except Exception:
            logger.exception("插件模块 import 失败喵: %s", module_name)
            return None

        meta = PluginMeta.of(module)
        if not meta.enabled:
            logger.info("插件 %s 自己写了 disabled，跳过喵~", meta.name)
            return None

        setup = getattr(module, "setup", None)
        if setup is not None:
            token = _CURRENT_PLUGIN.set(meta.name)
            try:
                result = setup(self.bot)
                if inspect.isawaitable(result):
                    result = await result
                # 三种写法都认：bot.on_teardown() 显式注册 > setup 返回值 > 模块级 teardown
                if callable(result):
                    self._teardowns.setdefault(meta.name, result)
                if meta.name not in self._teardowns:
                    fallback = getattr(module, "teardown", None)
                    if callable(fallback):
                        self._teardowns[meta.name] = fallback
            except Exception:
                logger.exception("插件 setup 走神了喵: %s", module_name)
                self.bot.dispatcher.remove_plugin(meta.name)
                return None
            finally:
                _CURRENT_PLUGIN.reset(token)
        else:
            logger.debug("插件 %s 没有 setup()，只打个照面就够啦喵", module_name)

        self.modules[module_name] = module
        self.loaded[meta.name] = meta
        logger.info("「%s」上线啦喵 (%s)", meta.name, module_name)
        return meta

    async def reload(self, plugin_name: str) -> PluginMeta | None:
        meta = self.loaded.pop(plugin_name, None)
        if meta is None:
            return None
        await self._run_teardown(plugin_name)
        self.bot.dispatcher.remove_plugin(plugin_name)
        self.modules.pop(meta.module, None)
        try:
            importlib.invalidate_caches()
            module = importlib.reload(importlib.import_module(meta.module))
        except Exception:
            logger.exception("插件重载翻车了喵: %s", plugin_name)
            return None
        self.modules[module.__name__] = module
        meta_new = PluginMeta.of(module)
        setup = getattr(module, "setup", None)
        if setup is not None:
            token = _CURRENT_PLUGIN.set(meta_new.name)
            try:
                result = setup(self.bot)
                if inspect.isawaitable(result):
                    result = await result
                # 三种写法都认：bot.on_teardown() 显式注册 > setup 返回值 > 模块级 teardown
                if callable(result):
                    self._teardowns.setdefault(meta_new.name, result)
                if meta_new.name not in self._teardowns:
                    fallback = getattr(module, "teardown", None)
                    if callable(fallback):
                        self._teardowns[meta_new.name] = fallback
            finally:
                _CURRENT_PLUGIN.reset(token)
        self.loaded[meta_new.name] = meta_new
        logger.info("插件重载成功喵 %s 焕然一新~", meta_new.name)
        return meta_new

    async def _run_teardown(self, plugin_name: str) -> None:
        teardown = self._teardowns.pop(plugin_name, None)
        if teardown is None:
            return
        try:
            result = teardown(self.bot)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("插件 %s 的 teardown 收拾不动喵:", plugin_name)

    async def unload_all(self) -> None:
        for name in list(self.loaded):
            await self._run_teardown(name)
            self.bot.dispatcher.remove_plugin(name)
        self.loaded.clear()
        self.modules.clear()
