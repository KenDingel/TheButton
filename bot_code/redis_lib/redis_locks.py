import os
import time
import asyncio
from typing import Optional
from .redis_client import redis_client
from utils.utils import logger


class RedisLock:
    """Async context manager for a simple Redis-based distributed lock.

    Usage:
        async with RedisLock(key=f"game:{game_id}:click_lock", timeout=5.0) as lock:
            if lock is None:
                # Redis down - fallback behavior
                pass
            else:
                # critical section
    """

    def __init__(self, key: str = None, game_id: Optional[int] = None, timeout: float = 5.0, retry_delay: float = 0.001):
        if key is None and game_id is None:
            raise ValueError("Either key or game_id must be provided")
        self.key = key or f"game:{game_id}:click_lock"
        self.timeout = float(timeout)
        self.retry_delay = float(retry_delay)
        self.identifier = f"{os.getpid()}:{time.time()}"
        self._client = None

    async def __aenter__(self):
        self._client = await redis_client.get_client()
        if not self._client:
            # Redis unavailable: signal caller by returning None so they can fallback
            logger.debug(f"Redis unavailable, lock fallback for {self.key}")
            return None

        end_time = time.time() + self.timeout
        while time.time() < end_time:
            try:
                # NX = set if not exists, ex = seconds
                result = await self._client.set(self.key, self.identifier, nx=True, ex=int(self.timeout))
                if result:
                    return self
            except Exception as e:
                logger.debug(f"RedisLock set error for {self.key}: {e}")
                return None

            await asyncio.sleep(self.retry_delay)

        raise TimeoutError(f"Could not acquire Redis lock for {self.key}")

    async def __aexit__(self, exc_type, exc, tb):
        if not self._client:
            return

        # Release lock only if identifier matches (atomic check+del via Lua)
        lua = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        else
            return 0
        end
        """
        try:
            await self._client.eval(lua, 1, self.key, self.identifier)
        except Exception as e:
            logger.debug(f"RedisLock release error for {self.key}: {e}")
