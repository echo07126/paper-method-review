"""极简进程内限流（滑动窗口），用于保护上传与审查等重接口。"""
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AppError

_WINDOWS: dict[str, deque] = defaultdict(deque)


def _hit(bucket: str, limit: int, window_seconds: int = 60) -> bool:
    now = time.monotonic()
    queue = _WINDOWS[bucket]
    while queue and now - queue[0] > window_seconds:
        queue.popleft()
    if len(queue) >= limit:
        return False
    queue.append(now)
    return True


def classify(path: str) -> tuple[str, int] | None:
    settings = get_settings()
    if path.endswith("/uploads"):
        return "uploads", settings.rate_limit_uploads_per_minute
    if path.endswith("/reviews"):
        return "reviews", settings.rate_limit_reviews_per_minute
    if path.endswith("/chat"):
        return "chat", settings.rate_limit_reads_per_minute
    return None


def enforce(request: Request) -> None:
    rule = classify(request.url.path)
    if not rule:
        return
    name, limit = rule
    session = request.cookies.get("pm_session", "anonymous")
    client = request.client.host if request.client else "unknown"
    for bucket in (f"{name}:{session}", f"{name}:ip:{client}"):
        if not _hit(bucket, limit):
            raise AppError("rate_limited", "请求过于频繁，请稍后重试。", 429)
