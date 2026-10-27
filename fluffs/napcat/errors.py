"""OneBot 11 协议层异常。

单独放一个模块，避免"传输实现"和"错误定义"绑在一起：
传输层、API 层、以及调用方（插件）都从这里取异常类型。
"""

from __future__ import annotations


class OneBotError(Exception):
    """OneBot 协议层异常基类。"""


class NotConnected(OneBotError):
    """当前没有可用的 NapCat 连接。"""


class ActionFailed(OneBotError):
    """NapCat 返回了失败状态。"""

    def __init__(self, action: str, retcode: int | None, message: str = "", wording: str = "", echo: object = None) -> None:
        detail = message or wording or "未知错误"
        super().__init__(f"API {action} 调用失败: retcode={retcode}, {detail}")
        self.action = action
        self.retcode = retcode
        self.message = message
        self.wording = wording
        self.echo = echo


class ActionTimeout(OneBotError):
    """等待 API 回包超时。"""

    def __init__(self, action: str, timeout: float) -> None:
        super().__init__(f"API {action} 等待回包超时（{timeout}s）")
        self.action = action
        self.timeout = timeout


__all__ = ["ActionFailed", "ActionTimeout", "NotConnected", "OneBotError"]
