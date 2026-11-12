"""传输层工厂与导出。"""

from __future__ import annotations

from ...config import ConnectionConfig
from ..errors import ActionFailed, ActionTimeout, NotConnected, OneBotError
from .base import EventHandler, StateHandler, Transport
from .forward_ws import ForwardWebSocketTransport
from .reverse_ws import ReverseWebSocketTransport

__all__ = [
    "ActionFailed",
    "ActionTimeout",
    "EventHandler",
    "NotConnected",
    "OneBotError",
    "StateHandler",
    "Transport",
    "create_transport",
]

_TRANSPORTS: dict[str, type[Transport]] = {
    "reverse_ws": ReverseWebSocketTransport,
    "forward_ws": ForwardWebSocketTransport,
}


def create_transport(
    config: ConnectionConfig,
    on_event: EventHandler,
    on_state_change: StateHandler | None = None,
) -> Transport:
    """按 ``connection.mode`` 创建传输实例。"""
    try:
        cls = _TRANSPORTS[config.mode]
    except KeyError:
        raise ValueError(f"未知的连接模式 {config.mode!r}，可选: {', '.join(_TRANSPORTS)}") from None
    return cls(config, on_event, on_state_change)
