import pytest
import time
from services.rate_limiter import RateLimiter


@pytest.fixture
def limiter():
    """Fresh RateLimiter instance per test (isolated fakeredis)."""
    return RateLimiter()


# ── basic allow / deny ────────────────────────────────────────────────────────

async def test_first_request_is_allowed(limiter):
    assert await limiter.check_limits(user_id=1, chat_id=100) is True


async def test_second_request_is_allowed(limiter):
    await limiter.check_limits(user_id=1, chat_id=100)
    assert await limiter.check_limits(user_id=1, chat_id=100) is True


async def test_different_users_are_independent(limiter):
    for _ in range(10):
        await limiter.check_limits(user_id=1, chat_id=100)
    # user 1 is exhausted; user 2 should still be allowed
    assert await limiter.check_limits(user_id=2, chat_id=100) is True


# ── per-user limit ────────────────────────────────────────────────────────────

async def test_per_user_limit_blocks_after_10_requests(limiter):
    user_id = 42
    chat_id = 999
    # Drain a separate global bucket by using many different users first
    # (isolate to just per-user behaviour by using unique chat+user per call)
    allowed = 0
    for i in range(15):
        if await limiter._is_allowed(f"user:{user_id}", max_tokens=10, refill_rate_per_sec=10/60):
            allowed += 1
    assert allowed == 10


# ── per-chat limit ────────────────────────────────────────────────────────────

async def test_per_chat_limit_blocks_after_50_requests(limiter):
    chat_id = 77
    allowed = 0
    for i in range(60):
        if await limiter._is_allowed(f"chat:{chat_id}", max_tokens=50, refill_rate_per_sec=50/60):
            allowed += 1
    assert allowed == 50


# ── token bucket refill ───────────────────────────────────────────────────────

async def test_token_bucket_starts_full(limiter):
    key = "test:bucket:start_full"
    # All 5 tokens available immediately
    allowed = 0
    for _ in range(7):
        if await limiter._is_allowed(key, max_tokens=5, refill_rate_per_sec=1.0):
            allowed += 1
    assert allowed == 5


async def test_is_allowed_returns_bool(limiter):
    result = await limiter._is_allowed("test:bool", max_tokens=1, refill_rate_per_sec=1.0)
    assert isinstance(result, bool)
    assert result is True


async def test_empty_bucket_returns_false(limiter):
    key = "test:empty"
    await limiter._is_allowed(key, max_tokens=1, refill_rate_per_sec=0.0)
    result = await limiter._is_allowed(key, max_tokens=1, refill_rate_per_sec=0.0)
    assert result is False
