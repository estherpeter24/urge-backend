"""Simple in-memory rate limiter for API endpoints"""
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import HTTPException, status, Request
from typing import Dict, Tuple
import asyncio


class RateLimiter:
    """
    Simple in-memory rate limiter.
    For production, use Redis-based rate limiting for distributed systems.
    """

    def __init__(self):
        # Store: {key: [(timestamp, count)]}
        self._requests: Dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_rate_limited(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> Tuple[bool, int]:
        """
        Check if a key is rate limited.

        Returns:
            Tuple of (is_limited, remaining_requests)
        """
        async with self._lock:
            now = datetime.utcnow()
            window_start = now - timedelta(seconds=window_seconds)

            # Clean old entries
            self._requests[key] = [
                ts for ts in self._requests[key]
                if ts > window_start
            ]

            current_count = len(self._requests[key])

            if current_count >= max_requests:
                return True, 0

            # Record this request
            self._requests[key].append(now)
            return False, max_requests - current_count - 1

    async def cleanup(self):
        """Remove old entries to prevent memory growth"""
        async with self._lock:
            now = datetime.utcnow()
            cutoff = now - timedelta(minutes=10)  # Keep 10 min window

            keys_to_delete = []
            for key, timestamps in self._requests.items():
                self._requests[key] = [ts for ts in timestamps if ts > cutoff]
                if not self._requests[key]:
                    keys_to_delete.append(key)

            for key in keys_to_delete:
                del self._requests[key]


# Global rate limiter instance
rate_limiter = RateLimiter()


async def check_rate_limit(
    request: Request,
    max_requests: int = 10,
    window_seconds: int = 60,
    key_prefix: str = ""
):
    """
    Dependency to check rate limit for an endpoint.

    Args:
        request: FastAPI request object
        max_requests: Maximum requests allowed in window
        window_seconds: Time window in seconds
        key_prefix: Optional prefix for rate limit key (e.g., endpoint name)
    """
    # Get client IP (handle proxies)
    client_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    # Create rate limit key
    key = f"{key_prefix}:{client_ip}" if key_prefix else client_ip

    is_limited, remaining = await rate_limiter.is_rate_limited(
        key, max_requests, window_seconds
    )

    if is_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Please try again later.",
            headers={"Retry-After": str(window_seconds)}
        )

    return remaining


# Pre-configured rate limit functions for common use cases
async def auth_rate_limit(request: Request):
    """Rate limit for auth endpoints: 5 requests per minute"""
    return await check_rate_limit(request, max_requests=5, window_seconds=60, key_prefix="auth")


async def api_rate_limit(request: Request):
    """Rate limit for general API endpoints: 100 requests per minute"""
    return await check_rate_limit(request, max_requests=100, window_seconds=60, key_prefix="api")


async def upload_rate_limit(request: Request):
    """Rate limit for upload endpoints: 20 uploads per minute"""
    return await check_rate_limit(request, max_requests=20, window_seconds=60, key_prefix="upload")
