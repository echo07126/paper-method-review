"""受控任务执行器：把重接口业务主体放进固定并发的线程池，任务状态落 jobs 表。

设计要点
--------
- **不用 `BackgroundTasks`**：后者无并发上限、不可按 id 查询、生命周期绑单次响应。
- **懒加载单例**：避免 `TestClient(app)` 不带 `with` 时不执行 lifespan 也能取到池；
  也让 `set_settings_override()` 的测试隔离（切换 db_path / worker 数）能在下一轮 `get_executor()` 生效。
- **异常只写进 job，不崩线程**：`AppError` 记 `{code, message}`，其他记 `internal_error`
  并只把堆栈写日志（不落正文）。
- `jobs` 表**不加列**：`kind/params/result/error` 全放 `payload` JSON，`state` 取
  `queued | running | succeeded | failed`。
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.logging import safe_logger
from app.storage.repository import Store

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"

_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None


def get_executor() -> ThreadPoolExecutor:
    """返回进程内共享的任务线程池（懒加载单例）。"""
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=max(1, get_settings().task_max_workers),
                thread_name_prefix="task",
            )
        return _executor


def shutdown_executor(wait: bool = False) -> None:
    """关闭线程池（lifespan 收尾调用）。置空以便下个应用上下文重建。"""
    global _executor
    with _lock:
        if _executor is not None:
            _executor.shutdown(wait=wait)
            _executor = None


def _run_job(store: Store, job_id: str, fn: Callable[[], Any]) -> None:
    store.mark_job_running(job_id)
    try:
        result = fn()
    except AppError as exc:
        store.finish_job(job_id, FAILED, {"error": {"code": exc.code, "message": exc.message}})
    except Exception:  # noqa: BLE001 - 任何异常都不得让工作线程崩溃
        safe_logger().exception("task_failed job_id=%s", job_id)
        store.finish_job(
            job_id, FAILED, {"error": {"code": "internal_error", "message": "任务执行失败，请稍后重试。"}}
        )
    else:
        store.finish_job(job_id, SUCCEEDED, {"result": result})


def submit(kind: str, session_id: str, params: dict, fn: Callable[[], Any]) -> str:
    """登记任务并入队，返回 `task_id`。

    `fn()` 的返回值即旧同步响应体，会被写进 `payload.result`；异常写进 `payload.error`。
    池已关闭时抛 503（不会留下永远 queued 的任务）。
    """
    store = Store(get_settings().db_path)
    job_id = new_id("job")
    store.create_job(job_id, session_id, kind, params)
    executor = get_executor()
    try:
        executor.submit(_run_job, store, job_id, fn)
    except RuntimeError:
        store.finish_job(job_id, FAILED, {"error": {"code": "service_unavailable", "message": "任务队列已关闭。"}})
        raise AppError("service_unavailable", "任务队列暂不可用，请稍后重试。", 503)
    return job_id