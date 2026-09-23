"""运行期数据生命周期：定期清理任务、保留期下限、孤儿临时目录回收。"""
import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.storage.db import connect, init_db
from app.storage.maintenance import cleanup_expired
from app.storage.repository import Store
from app.storage.cleanup_task import periodic_cleanup


def _make_session(db_path: str, tmp_root: Path, session_id: str) -> None:
    user_dir = tmp_root / session_id
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "paper.docx").write_bytes(b"PK\x03\x04fake")


def test_cleanup_respects_retention_floor(tmp_path: Path) -> None:
    """DATA_RETENTION_HOURS 是保留期下限：TTL 更长时按更长者执行。"""
    db_path = str(tmp_path / "app.db")
    temp_dir = tmp_path / "tmp"
    init_db(db_path)
    store = Store(db_path)
    session_id, _ = store.create_session(ttl_hours=24)  # TTL 24h，不会因过期被删

    _make_session(db_path, temp_dir, session_id)
    connection = connect(db_path)
    try:
        # 人为把创建时间推到 10 小时前，超过 2h 保留期下限
        old = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
        connection.execute("UPDATE sessions SET created_at = ? WHERE id = ?", (old, session_id))
        connection.commit()
    finally:
        connection.close()

    result = cleanup_expired(db_path, str(temp_dir), retention_hours=2)
    assert result["removed_sessions"] == 1
    assert not (temp_dir / session_id).exists()


def test_cleanup_keeps_live_session_and_its_files(tmp_path: Path) -> None:
    """未过期且未超保留期的会话及其临时文件必须保留。"""
    db_path = str(tmp_path / "app.db")
    temp_dir = tmp_path / "tmp"
    init_db(db_path)
    store = Store(db_path)
    session_id, _ = store.create_session(ttl_hours=2)
    _make_session(db_path, temp_dir, session_id)

    result = cleanup_expired(db_path, str(temp_dir), retention_hours=2)
    assert result["removed_sessions"] == 0
    assert (temp_dir / session_id / "paper.docx").exists()


def test_cleanup_removes_orphan_temp_dirs(tmp_path: Path) -> None:
    """数据库中已无记录的临时子目录（进程被杀等泄漏）必须被回收。"""
    db_path = str(tmp_path / "app.db")
    temp_dir = tmp_path / "tmp"
    init_db(db_path)
    orphan = temp_dir / "sess_leaked_deadbeef"
    orphan.mkdir(parents=True)
    (orphan / "leftover.docx").write_bytes(b"PK\x03\x04")

    result = cleanup_expired(db_path, str(temp_dir), retention_hours=2)
    assert result["removed_temp_dirs"] == 1
    assert not orphan.exists()


def test_periodic_cleanup_runs_and_cancels(tmp_path: Path) -> None:
    """常驻清理任务：至少执行一轮，且取消后能优雅退出（不抛 CancelledError）。"""
    db_path = str(tmp_path / "app.db")
    temp_dir = tmp_path / "tmp"
    init_db(db_path)
    orphan = temp_dir / "sess_orphan_for_periodic"
    orphan.mkdir(parents=True)

    async def scenario() -> None:
        task = asyncio.create_task(periodic_cleanup(db_path, str(temp_dir), interval_seconds=1))
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and orphan.exists():
            await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert not orphan.exists()
