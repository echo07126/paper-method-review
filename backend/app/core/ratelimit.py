"""极简进程内限流（滑动窗口），用于保护上传与审查等重接口。"""
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AppError
from app.storage.repository import Store

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
    # 重接口共用 reviews 桶：审查、修改稿二次审查、对比审查均为触发模型的高成本调用
    if path.endswith("/reviews") or path.endswith("/revision") or path.endswith("/compare"):
        return "reviews", settings.rate_limit_reviews_per_minute
    if path.endswith("/chat"):
        return "chat", settings.rate_limit_reads_per_minute
    return None


def _session_key(request: Request) -> str:
    """限流桶键只用「已登记且未过期」的会话。

    直接取原始 cookie 值会被轮换伪造值绕过；这里回查存储，无效/不存在的
    token 一律归入匿名桶，使伪造 cookie 无法获得独立配额。
    """
    token = request.cookies.get("pm_session", "")
    if not token:
        return "anonymous"
    try:
        session_id = Store(get_settings().db_path).get_session_by_token(token)
    except Exception:  # noqa: BLE001 - 限流不应因存储异常影响主流程
        return "anonymous"
    return session_id or "anonymous"


def enforce(request: Request) -> None:
    rule = classify(request.url.path)
    if not rule:
        return
    name, limit = rule
    session = _session_key(request)
    client = request.client.host if request.client else "unknown"
    for bucket in (f"{name}:{session}", f"{name}:ip:{client}"):
        if not _hit(bucket, limit):
            raise AppError("rate_limited", "请求过于频繁，请稍后重试。", 429)
