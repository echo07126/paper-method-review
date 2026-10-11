"""任务生命周期清理：终态旧任务与僵尸任务按 TASK_RETENTION_MINUTES 清除，近期任务保留。"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.storage.db import connect, init_db
from app.storage.maintenance import cleanup_expired
from app.storage.repository import Store


def test_cleanup_removes_stale_and_zombie_jobs(tmp_path: Path) -> None:
    db_path = str(tmp_path / "app.db")
    temp_dir = tmp_path / "tmp"
    init_db(db_path)
    store = Store(db_path)
    session_id, _ = store.create_session(ttl_hours=24)

    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    store.create_job("job_done_old", session_id, "review", {})
    store.finish_job("job_done_old", "succeeded", {"result": {}})
    store.create_job("job_failed_old", session_id, "review", {})
    store.finish_job("job_failed_old", "failed", {"error": {}})
    # 僵尸任务：进程被杀后永远留在 queued/running 的残留
    store.create_job("job_zombie", session_id, "review", {})
    # 近期终态任务：必须保留
    store.create_job("job_recent", session_id, "review", {})
    store.finish_job("job_recent", "succeeded", {"result": {}})

    connection = connect(db_path)
    try:
        connection.execute(
            "UPDATE jobs SET updated_at = ? WHERE id IN ('job_done_old', 'job_failed_old')", (old,)
        )
        connection.execute("UPDATE jobs SET created_at = ? WHERE id = 'job_zombie'", (old,))
        connection.commit()
    finally:
        connection.close()

    result = cleanup_expired(db_path, str(temp_dir), retention_hours=2)
    assert result["removed_jobs"] == 3

    connection = connect(db_path)
    try:
        remaining = {row["id"] for row in connection.execute("SELECT id FROM jobs").fetchall()}
    finally:
        connection.close()
    assert remaining == {"job_recent"}