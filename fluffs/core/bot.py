"""
    bot.on_command("xxx")     注册命令
    ctx.reply("...")          回复
    bot.api.*                 主动调用 OneBot 接口
    bot.services["名字"]      模块之间共享可复用对象
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from ..config import FluffsConfig
from ..napcat import BotAPI, create_transport
from ..napcat.events import Event, parse_event
from .context import EventContext
from .dispatcher import (
    KIND_ALL,
    KIND_MESSAGE,
    KIND_META,
    KIND_NOTICE,
    KIND_REQUEST,
    Dispatcher,
    Handler,
    HandlerFunc,
)
from .loader import PluginManager, current_plugin
from .rules import Rule

logger = logging.getLogger(__name__)


class FluffsBot:
    def __init__(self, config: FluffsConfig) -> None:
        self.config = config
        self.transport = create_transport(
            config.connection,
            on_event=self._on_raw_event,
            on_state_change=self._on_state_change,
        )
        self.api = BotAPI(self.transport, self_id=config.bot.self_id)
        self.dispatcher = Dispatcher()
        self.plugins = PluginManager(self)
        # 模块之间共享可复用对象（如聊天记录归档），用 bot.services["名字"] 取用
        self.services: dict[str, Any] = {}
        self._stop_event = asyncio.Event()
        self._bg_tasks: set[asyncio.Task[Any]] = set()
        self._started = False

    # 状态
    @property
    def ready(self) -> bool:
        """是否已连上 NapCat"""
        return self.transport.ready

    # 通用触发入口（模块与插件用这些注册）
    def on_message(self, rule: Rule | None = None, **kwargs: Any) -> Callable[[HandlerFunc], HandlerFunc]:
        """消息事件；rule 传 None 表示所有消息。"""
        return self.dispatcher.on_message(rule, plugin=current_plugin(), **kwargs)

    def on_command(self, *names: str, rule: Rule | None = None, **kwargs: Any) -> Callable[[HandlerFunc], HandlerFunc]:
        """命令处理：@bot.on_command("echo") 命中 /echo、#echo。

        可传 prefixes=[""] 表示不带前缀；命中后参数在 ctx.args / ctx.argv。
        """
        from .rules import command

        prefixes = kwargs.pop("prefixes", None)
        ignore_case = kwargs.pop("ignore_case", False)
        extra_rule = rule
        cmd_rule = command(*names, prefixes=prefixes, ignore_case=ignore_case)
        combined = cmd_rule if extra_rule is None else (lambda ctx: cmd_rule(ctx) and bool(extra_rule(ctx)))
        return self.dispatcher.on_message(combined, plugin=current_plugin(), **kwargs)

    def on_notice(self, rule: Rule | None = None, **kwargs: Any) -> Callable[[HandlerFunc], HandlerFunc]:
        """通知事件：戳一戳、群成员变动、撤回等。"""
        return self.dispatcher.on_notice(rule, plugin=current_plugin(), **kwargs)

    def on_request(self, rule: Rule | None = None, **kwargs: Any) -> Callable[[HandlerFunc], HandlerFunc]:
        """请求事件：加好友 / 加群。"""
        return self.dispatcher.on_request(rule, plugin=current_plugin(), **kwargs)

    def on_meta(self, rule: Rule | None = None, **kwargs: Any) -> Callable[[HandlerFunc], HandlerFunc]:
        """元事件：生命周期、心跳。"""
        return self.dispatcher.on_meta(rule, plugin=current_plugin(), **kwargs)

    def on_event(self, rule: Rule | None = None, **kwargs: Any) -> Callable[[HandlerFunc], HandlerFunc]:
        """通配：任何事件都会进来。"""
        return self.dispatcher.on_event(rule, plugin=current_plugin(), **kwargs)

    def on_teardown(self, func: Callable[[FluffsBot], Any]) -> None:
        """注册本插件的卸载钩子；只能在插件的 setup() 里调用。

        没有资源要释放的插件不用写；有资源的用这个，比「setup 返回一个函数」直白，
        也让 setup 可以老老实实标注 -> None

            def setup(bot) -> None:
                bot.on_teardown(cleanup)   # async def cleanup(bot) -> None
        """
        if not self.plugins.add_teardown(func):
            logger.warning("on_teardown() 只能写在插件的 setup() 里,这次注册被丢弃喵")

    # 生命周期
    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await self.plugins.load_all()
        await self.transport.start()
        logger.info("Fluffs 启动好啦喵 等待 NapCat 连线~")

    async def run(self) -> None:
        """启动并阻塞，直到 request_stop() / 收到中断"""
        await self.start()
        await self._stop_event.wait()
        await self.stop()

    def request_stop(self) -> None:
        """请求退出"""
        self._stop_event.set()

    async def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        await self.transport.stop()
        for task in list(self._bg_tasks):
            task.cancel()
        if self._bg_tasks:
            await asyncio.gather(*self._bg_tasks, return_exceptions=True)
        await self.plugins.unload_all()
        self.services.clear()
        logger.info("Fluffs 收工啦喵")

    # 事件入口
    async def _on_raw_event(self, raw: dict[str, Any]) -> None:
        try:
            event = parse_event(raw)
        except Exception:
            logger.exception("这条事件啃不动，先放一边啦喵 原始报文: %.300s", raw)
            return

        if not self.api.self_id and event.self_id:
            self.api.self_id = event.self_id
            logger.info("从事件里认出自己啦 登录账号: %s", self.api.self_id)

        if event.post_type == "meta_event":
            logger.debug("收到一枚元事件~ %s", event.get("meta_event_type"))

        # 机器人自己发出的消息不进分发（防自触发循环，见 config.bot.ignore_self）
        if self.config.bot.ignore_self and self._is_self_message(event):
            logger.debug("这是我自己说的话呀，跳过跳过: %.100s", event.get("raw_message"))
            return

        await self.dispatcher.dispatch(self, event)

    def _is_self_message(self, event: Event) -> bool:
        """判断这条消息是否由机器人自己发出。

        只在 user_id == self_id 时才成立（群消息里就是自己发的那条）。
        自己发的消息可能以 message 或 message_sent 上报，两种都拦住。
        """
        if not self.api.self_id:
            return False
        if event.post_type == "message_sent":
            return True
        if event.post_type != "message":
            return False
        return event.get("user_id") == self.api.self_id

    async def _on_state_change(self, connected: bool) -> None:
        """连接状态变化回调。

        必须立刻返回：协议层是在收包循环开始前 await 这个回调的，
        如果在里面 await API 调用，会造成"回包没人读 -> 卡死"的死锁。
        所以查询类工作放到后台任务里做。
        """
        if not connected:
            return
        task = asyncio.create_task(self._after_connect(), name="fluffs-after-connect")
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _after_connect(self) -> None:
        """连上 NapCat 后补齐登录信息 / 版本信息（失败不影响运行）。"""
        if not self.api.self_id:
            try:
                info = await self.api.get_login_info()
                self.api.self_id = int(info.get("user_id") or 0)
                logger.info("身份确认完毕喵 登录账号: %s (%s)", self.api.self_id, info.get("nickname", ""))
            except Exception as exc:
                logger.warning("唔，登录信息没拿到喵: %s", exc)
        try:
            version = await self.api.get_version_info()
            logger.info("NapCat 版本确认: %s 喵~", version.get("app_name") or version)
        except Exception:
            logger.debug("版本信息没拿到，不过不影响运行喵~", exc_info=True)

    # --- 调试辅助 ---------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        """运行状态摘要（/status 用）。"""
        return {
            "ready": self.ready,
            "self_id": self.api.self_id,
            "handlers": len(self.dispatcher.handlers),
            "plugins": [meta.name for meta in self.plugins.loaded.values()],
            "services": sorted(self.services),
            "kinds": [KIND_MESSAGE, KIND_NOTICE, KIND_REQUEST, KIND_META, KIND_ALL],
        }


__all__ = ["FluffsBot", "Handler", "HandlerFunc"]
