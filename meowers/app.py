# App program entrance

from __future__ import annotations

import asyncio
import logging

import fluffs
from fluffs import FluffsBot
from fluffs.logging_setup import setup_logging

from . import __version__
from .config import load_config

logger = logging.getLogger(__name__)


def main() -> int:
    config = load_config()
    setup_logging(config.log.level, config.log.file)

    logger.info("MeowersBot v%s 启动完成啦喵 框架是 Fluffs v%s ~", __version__, fluffs.__version__)
    for key, value in config.summary().items():
        logger.info("  配置 %s = %s 喵", key, value)

    bot = FluffsBot(config)
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C 啦，朱波下播啦喵~")
        return 130
    except Exception:
        logger.exception("呜…出现了没预料到的错误喵")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
