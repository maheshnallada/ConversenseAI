import os
import threading
import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class ConcurrencyLimiter(Protocol):
    def acquire(self, timeout_s: float = 10.0) -> bool:
        ...

    def release(self) -> None:
        ...


class InMemoryConcurrencyLimiter:
    def __init__(self, max_concurrency: int = 15) -> None:
        self._semaphore = threading.Semaphore(max_concurrency)

    def acquire(self, timeout_s: float = 10.0) -> bool:
        return self._semaphore.acquire(timeout=timeout_s)

    def release(self) -> None:
        try:
            self._semaphore.release()
        except ValueError:
            pass


class RedisConcurrencyLimiter:
    """Distributed concurrency limiter using Redis with auto-expiring leases."""

    def __init__(
        self,
        redis_client,
        key: str = "limiter:evaluation:slots",
        max_concurrency: int = 15,
        lease_ttl_s: int = 60,
    ) -> None:
        self._redis = redis_client
        self._key = key
        self._max = max_concurrency
        self._lease_ttl = lease_ttl_s
        self._acquired_tokens: set[str] = set()

    def acquire(self, timeout_s: float = 10.0) -> bool:
        start = time.time()
        import uuid

        token = str(uuid.uuid4())
        while time.time() - start < timeout_s:
            now = time.time()
            # Clean expired tokens older than now - lease_ttl
            self._redis.zremrangebyscore(self._key, "-inf", now - self._lease_ttl)
            # Count active tokens
            active_count = self._redis.zcard(self._key)
            if active_count < self._max:
                # Add token with current timestamp score
                if self._redis.zadd(self._key, {token: now}, nx=True):
                    self._acquired_tokens.add(token)
                    return True
            time.sleep(0.1)
        return False

    def release(self) -> None:
        if not self._acquired_tokens:
            return
        token = self._acquired_tokens.pop()
        try:
            self._redis.zrem(self._key, token)
        except Exception:
            pass


def get_concurrency_limiter(
    key: str = "limiter:evaluation:slots",
    max_concurrency: int = 15,
) -> ConcurrencyLimiter:
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis
            client = redis.Redis.from_url(redis_url)
            client.ping()
            return RedisConcurrencyLimiter(client, key=key, max_concurrency=max_concurrency)
        except Exception:
            pass
    return InMemoryConcurrencyLimiter(max_concurrency=max_concurrency)
