from __future__ import annotations

import asyncio
import platform
import socket
import subprocess
import time
from datetime import timedelta

import psutil

from fluffs.config import get_active_config
from fluffs.core import EventContext

_cfg = get_active_config()
_prefixes = _cfg.bot.command_prefixes if _cfg else []
command_prefix = (_prefixes or ["//"])[0]

__plugin_meta__ = {
    "name": "sys_query",
    "description": "查询电脑系统状态",
    "usage": f"{command_prefix}查询",
    "version": "1.5.0",
    "author": "Eriser",
}

GB = 1024 ** 3
MB = 1024 ** 2


def _fmt_size(n: float) -> str:
    return f"{n / GB:.1f}G" if n >= GB else f"{n / MB:.1f}M"


def _fmt_uptime(seconds: float) -> str:
    td = timedelta(seconds=int(seconds))
    h, m = td.seconds // 3600, (td.seconds % 3600) // 60
    if td.days:
        return f"{td.days}天{h}小时{m}分"
    if h:
        return f"{h}小时{m}分"
    return f"{m}分"


def _bar(pct: float, width: int = 10) -> str:
    filled = max(0, min(width, int(pct / 100 * width + 0.5)))
    return "█" * filled + "░" * (width - filled)


def _cpu_name() -> str:
    system = platform.system()
    try:
        if system == "Windows":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_Processor).Name"],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip().splitlines()[0].strip()
        elif system == "Linux":
            with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        elif system == "Darwin":
            out = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                 capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                return out.stdout.strip()
    except Exception:
        pass
    return platform.processor() or "未知 CPU"


def _disk_lines() -> list[str]:
    lines = []
    for p in psutil.disk_partitions(all=False):
        if not p.fstype or "cdrom" in p.opts:
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except (PermissionError, OSError):
            continue
        lines.append(
            f"{p.mountpoint}  {u.percent:.1f}%  {_bar(u.percent)}  "
            f"{_fmt_size(u.used)} / {_fmt_size(u.total)}"
        )
    return lines or ["读取失败"]


def _gpu_line() -> str:
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            rows = out.stdout.strip().splitlines()
            g = rows[0].split(", ")
            suffix = f"  ·  共 {len(rows)} 张" if len(rows) > 1 else ""
            return f"{g[0]}%  ·  {g[1]} / {g[2]} MB  ·  {g[3]}°C{suffix}"
    except Exception:
        pass
    return "无 N 卡或驱动异常"


def _top_procs(procs) -> list[tuple[str, float]]:
    logical = psutil.cpu_count(logical=True) or 1
    idle = {"system idle process", "idle"}
    entries = []
    for p in procs:
        try:
            if p.pid == 0 or (p.name() or "").lower() in idle:
                continue
            entries.append((p.cpu_percent(None) / logical, p.pid, p.name() or "?"))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    entries.sort(key=lambda x: x[0], reverse=True)
    entries = [e for e in entries if e[0] >= 0.1]
    return [(name, cpu) for cpu, _pid, name in entries[:3]]


def _collect() -> str:
    procs = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            p.cpu_percent(None)
            procs.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    per_cpu = psutil.cpu_percent(interval=0.6, percpu=True)
    cpu = sum(per_cpu) / len(per_cpu) if per_cpu else 0.0

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    freq = psutil.cpu_freq()
    freq_str = f"{freq.current / 1000:.2f}GHz" if freq else "N/A"

    physical = psutil.cpu_count(logical=False) or 0
    logical = psutil.cpu_count(logical=True) or 0

    lines = [
        f"   {socket.gethostname()}",
        f"    系统  {platform.system()} {platform.release()} · "
        f"运行 {_fmt_uptime(time.time() - psutil.boot_time())}",
        f"    CPU  {_cpu_name()}",
        f"    使用率 {cpu:.1f}%  {_bar(cpu)}",
        f"    {freq_str} · {physical}C{logical}T",
        f"   RAM  {mem.percent:.1f}%  {_bar(mem.percent)}",
        f"    {_fmt_size(mem.used)} / {_fmt_size(mem.total)} · Swap {swap.percent:.1f}%",
        "   SSD",
        *[f"    {line}" for line in _disk_lines()],
        f"   GPU  {_gpu_line()}",
    ]

    top = _top_procs(procs)
    if top:
        lines.append("   Top CPU")
        w = min(max(len(n) for n, _ in top), 20)
        for name, c in top:
            if len(name) > 20:
                name = name[:19] + "…"
            lines.append(f"    {name.ljust(w)}  {c:.1f}%")

    return "\n".join(lines)


def setup(bot) -> None:
    @bot.on_command("查询","query")
    async def query_status(ctx: EventContext) -> None:
        try:
            info = await asyncio.to_thread(_collect)
        except Exception as e:
            info = f"读取系统状态失败: {e!r}"
        await ctx.reply(info)