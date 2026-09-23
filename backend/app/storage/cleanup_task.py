"""运行期定期清理：后台协程周期性执行 `cleanup_expired`。

设计取舍
--------
- 单机有效：与「单机 SQLite + 进程内限流」的现有取舍一致；多实例部署前需改为
  共享存储 + 单一调度（已在运维文档中登记为已知取舍）。
- 不引入 APScheduler 等新依赖：用 asyncio 原生任务，保持依赖面最小。
- 异常隔离：单轮清理失败不影响后续轮次，也不影响服务主流程。
- 优雅退出：收到取消信号时记录日志后正常结束，不抛出 CancelledError。
"""
import asyncio

from app.core.logging import safe_logger
from app.storage.maintenance import cleanup_expired

# 清理间隔（秒）。会话 TTL 默认 2 小时，取 300s（5 分钟）可在 TTL 到期后及时回收，
# 同时把每轮开销（两次 SQLite 连接 + 一次目录遍历）控制在可忽略范围。
CLEANUP_INTERVAL_SECONDS = 300


async def periodic_cleanup(db_path: str, temp_dir: str, interval_seconds: int = CLEANUP_INTERVAL_SECONDS) -> None:
    """周期性清理过期会话与临时文件；随应用生命周期取消而退出。"""
    logger = safe_logger()
    logger.info("periodic_cleanup started interval=%ss", interval_seconds)
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                result = cleanup_expired(db_path, temp_dir)
                logger.info("periodic_cleanup done %s", result)
            except Exception as exc:  # noqa: BLE001
                logger.warning("periodic_cleanup failed %s", exc)
    except asyncio.CancelledError:
        logger.info("periodic_cleanup stopped")
        raise
