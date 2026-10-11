"""重接口异步任务化：受控线程池 + jobs 表持久化（POST 202 + 轮询 /tasks/{id}）。"""
from app.tasks.executor import get_executor, shutdown_executor, submit

__all__ = ["get_executor", "shutdown_executor", "submit"]