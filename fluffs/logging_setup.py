"""日志初始化：控制台在终端下用 coloredlogs 上色，文件保持纯文本。
coloredlogs 会给时间、级别、logger 名和消息分别上色；输出被重定向到文件或管道时
退回普通 ``StreamHandler``——不往文件里写 ANSI 控制字符，也不按宽度折行。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import coloredlogs

FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-24s | %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"

# 这些第三方库固定降噪到 WARNING，即使 level=DEBUG 也看不到它们的调试输出
QUIET_LOGGERS = ("websockets", "httpx", "httpcore", "aiosqlite")


def setup_logging(level: str = "INFO", log_file: str = "") -> None:
    """配置根 logger：控制台（终端下彩色，重定向后纯文本）+ 可选文件。"""
    root = logging.getLogger()
    level_no = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(level_no)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    if sys.stdout.isatty():
        # 终端：coloredlogs 的 ColoredFormatter（时间/级别/logger/消息按级别配色）。
        # isatty=True 是显式授权上色：是否彩色已由上面这一行判定，不再让 NO_COLOR 之类的
        # 环境变量把颜色二次掐掉（重定向的场景在下面的 else 分支里）。
        coloredlogs.install(
            level=level_no,
            logger=root,
            fmt=FORMAT,
            datefmt=DATEFMT,
            stream=sys.stdout,
            isatty=True,
        )
    else:
        screen = logging.StreamHandler(sys.stdout)
        screen.setFormatter(logging.Formatter(FORMAT, datefmt=DATEFMT))
        root.addHandler(screen)

    if log_file:
        path = Path(log_file)
        if not path.is_absolute():
            path = Path.cwd() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(FORMAT, datefmt=DATEFMT))
        root.addHandler(file_handler)

    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
