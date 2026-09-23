"""维护任务：清理过期会话与其临时文件（数据生命周期落地）。

清理范围与口径
--------------
- 会话过期判定：`sessions.expires_at < now`（`SESSION_TTL_HOURS`，默认 2 小时）。
- 临时文件残留：`TEMP_DIR` 下**不属于任何存活会话**的子目录一律删除，
  覆盖进程被杀、异常退出等导致的泄漏。
- 数据库内文档正文（`documents.ir_json`）随会话过期一并删除，
  与「正文仅在本次会话内暂存」的隐私口径一致。
- `DATA_RETENTION_HOURS` 作为保留期下限：即使会话未过期，超过该时长的数据也一并清理。
"""
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.audit import audit
from app.core.config import get_settings
from app.core.logging import safe_logger
from app.storage.db import connect


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _purge_session_rows(connection, session_ids: list[str]) -> None:
    for session_id in session_ids:
        connection.execute("DELETE FROM reports WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM documents WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM jobs WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def cleanup_expired(db_path: str, temp_dir: str, retention_hours: int | None = None) -> dict:
    """清理过期会话、超保留期数据与孤儿临时目录。

    `retention_hours` 为 None 时取 `DATA_RETENTION_HOURS`（默认 2 小时）；
    该值为保留期下限，实际生效取 `max(SESSION_TTL_HOURS, DATA_RETENTION_HOURS)`。
    """
    now = _now()
    settings = get_settings()
    if retention_hours is None:
        retention_hours = max(settings.data_retention_hours, settings.session_ttl_hours)
    cutoff = (now - timedelta(hours=retention_hours)).isoformat()

    connection = connect(db_path)
    try:
        rows = connection.execute("SELECT id FROM sessions WHERE expires_at < ? OR created_at < ?", (now.isoformat(), cutoff)).fetchall()
        expired_ids = [row["id"] for row in rows]
        _purge_session_rows(connection, expired_ids)
        connection.commit()
    finally:
        connection.close()

    # 孤儿临时目录：不属于任何存活会话的子目录一律删除
    connection = connect(db_path)
    try:
        known = {row["id"] for row in connection.execute("SELECT id FROM sessions").fetchall()}
    finally:
        connection.close()

    removed_dirs = 0
    root = Path(temp_dir)
    if root.exists():
        for directory in root.iterdir():
            if directory.is_dir() and directory.name not in known:
                shutil.rmtree(directory, ignore_errors=True)
                removed_dirs += 1

    result = {
        "removed_sessions": len(expired_ids),
        "removed_temp_dirs": removed_dirs,
        "retention_hours": retention_hours,
    }
    safe_logger().info("maintenance cleanup done %s", result)
    audit("startup_cleanup", removed_sessions=result["removed_sessions"], removed_temp_dirs=removed_dirs)
    return result
