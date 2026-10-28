"""群友头像下载与磁盘缓存
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import httpx

from fluffs.napcat import avatar_url

logger = logging.getLogger(__name__)

DEFAULT_DIR = Path("data/avatars")
DEFAULT_TTL = 7 * 24 * 3600
DEFAULT_SIZE = 640


class AvatarCache:
    """头像下载 + 磁盘缓存。
    超过ttl秒后下次取用会自动重拉。对同一个 (user_id, size) 的并发请求
    只下载一次，其余等同一个 future，避免重复打 CDN
    """

    def __init__(
        self,
        cache_dir: Path | str = DEFAULT_DIR,
        ttl: float = DEFAULT_TTL,
        timeout: float = 15.0,
        base_dir: Path | None = None,
    ) -> None:
        self.dir = Path(cache_dir)
        if not self.dir.is_absolute() and base_dir is not None:
            self.dir = base_dir / self.dir
        self.ttl = ttl
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._in_flight: dict[tuple[int, int], asyncio.Future[bytes]] = {}
        self.hits = 0
        self.misses = 0
        self.failures = 0

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)
        return self._client

    def _path(self, user_id: int, size: int) -> Path:
        return self.dir / f"{user_id}_{size}.jpg"

    def _fresh(self, path: Path) -> bool:
        try:
            return time.time() - path.stat().st_mtime < self.ttl
        except OSError:
            return False

    async def get(self, user_id: int, size: int = DEFAULT_SIZE) -> bytes:
        """返回头像字节；优先读磁盘缓存，过期 / 缺失时下载并落盘"""
        key = (int(user_id), int(size))
        path = self._path(*key)
        if path.is_file() and self._fresh(path):
            self.hits += 1
            return path.read_bytes()

        if key in self._in_flight:
            return await self._in_flight[key]

        future: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        self._in_flight[key] = future
        try:
            data = await self._download(user_id, size)
            self.dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self.misses += 1
            future.set_result(data)
            return data
        except Exception as exc:
            self.failures += 1
            future.set_exception(exc)
            raise
        finally:
            self._in_flight.pop(key, None)

    async def _download(self, user_id: int, size: int) -> bytes:
        url = avatar_url(user_id, size)
        response = await self._get_client().get(url)
        response.raise_for_status()
        data = response.content
        if not data:
            raise RuntimeError(f"头像下载回来是空的喵: {url}")
        return data

    def clear(self, user_id: int | None = None) -> int:
        """清缓存,user_id给None时清空整个目录，返回删除文件数"""
        if not self.dir.is_dir():
            return 0
        pattern = f"{int(user_id)}_*.jpg" if user_id is not None else "*.jpg"
        removed = 0
        for path in self.dir.glob(pattern):
            try:
                path.unlink()
                removed += 1
            except OSError:
                logger.debug("清理头像缓存时没删掉喵: %s", path)
        return removed

    def stats(self) -> dict:
        cached = len(list(self.dir.glob("*.jpg"))) if self.dir.is_dir() else 0
        return {
            "dir": str(self.dir),
            "ttl_days": round(self.ttl / 86400, 1),
            "cached": cached,
            "hits": self.hits,
            "misses": self.misses,
            "failures": self.failures,
        }

    def status_line(self) -> str:
        data = self.stats()
        return f"{data['cached']} 张已缓存 · 命中 {self.hits} / 下载 {self.misses}（{data['ttl_days']} 天过期）"

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


__all__ = ["AvatarCache", "DEFAULT_SIZE", "DEFAULT_TTL"]
