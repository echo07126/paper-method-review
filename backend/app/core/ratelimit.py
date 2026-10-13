"""极简进程内限流（滑动窗口），用于保护上传与审查等重接口。"""
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AppError
from app.storage.repository import Store

_WINDOWS: dict[str, deque] = defaultdict(deque)
# 桶键按「接口类别 + 会话/客户端」划分，会话一多键就无界增长。定期清掉已过期/已空的桶，
# 避免长期驻留的服务把内存耗在再也不会被命中的限流桶上。
_PRUNE_EVERY = 512
_calls = 0


def _prune(now: float, window_seconds: int) -> None:
    stale = [
        bucket
        for bucket, queue in _WINDOWS.items()
        if not queue or now - queue[-1] > window_seconds
    ]
    for bucket in stale:
        del _WINDOWS[bucket]


def _hit(bucket: str, limit: int, window_seconds: int = 60) -> bool:
    global _calls
    now = time.monotonic()
    _calls += 1
    if _calls % _PRUNE_EVERY == 0:
        _prune(now, window_seconds)
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
