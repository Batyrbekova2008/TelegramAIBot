import time
import fakeredis.aioredis as fake_aioredis

class RateLimiter:
    def __init__(self):
        # Нағыз Redis орнына виртуалды fakeredis қолданамыз
        self.redis = fake_aioredis.FakeRedis(decode_responses=True)

    async def _is_allowed(self, key: str, max_tokens: int, refill_rate_per_sec: float) -> bool:
        now = time.time()
        bucket_key = f"ratelimit:bucket:{key}"
        last_update_key = f"ratelimit:ts:{key}"

        pipe = self.redis.pipeline()
        pipe.get(bucket_key)
        pipe.get(last_update_key)
        res_bucket, res_ts = await pipe.execute()

        last_ts = float(res_ts) if res_ts else now
        tokens = float(res_bucket) if res_bucket else float(max_tokens)

        delta = max(0.0, now - last_ts)
        tokens = min(float(max_tokens), tokens + delta * refill_rate_per_sec)

        if tokens >= 1.0:
            tokens -= 1.0
            pipe = self.redis.pipeline()
            pipe.set(bucket_key, tokens)
            pipe.set(last_update_key, now)
            await pipe.execute()
            return True
        return False

    async def check_limits(self, user_id: int, chat_id: int) -> bool:
        # Per-user: 10 запросов/минуту
        if not await self._is_allowed(f"user:{user_id}", max_tokens=10, refill_rate_per_sec=10/60):
            return False
        # Per-chat: 50 запросов/минуту
        if not await self._is_allowed(f"chat:{chat_id}", max_tokens=50, refill_rate_per_sec=50/60):
            return False
        # Global Groq RPM
        if not await self._is_allowed("global_groq", max_tokens=30, refill_rate_per_sec=30/60):
            return False
        return True

rate_limiter = RateLimiter()