"""备份与删除传播验证：生产上线前/后各跑一次，确认「删除传播」真实生效。

用法:
    python backend/scripts/backup_check.py                 # 只做删除传播验证（不动备份）
    python backend/scripts/backup_check.py --backup-dir /var/backups/pmr
    python backend/scripts/backup_check.py --backup-dir /var/backups/pmr --create-backup

说明:
- 本脚本使用隔离的临时数据库，不会触碰真实 ./data。
- 删除传播验证：灌入会话 -> 上传件 + 结构化正文 + 追问历史 -> purge -> 逐项断言五张表与该会话
  临时目录都为空。
- 备份验证（--create-backup）：用 sqlite3 的 backup API 生成数据库快照，并校验快照可读、
  且快照内仍能查到该会话数据（证明备份侧需要独立的删除传播策略，见上线待办第 4 项）。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from pydantic_settings import SettingsConfigDict  # noqa: E402

from app.core.config import Settings, set_settings_override  # noqa: E402
from app.storage.db import init_db  # noqa: E402
from app.storage.files import purge_session_files, save_upload  # noqa: E402
from app.storage.repository import Store  # noqa: E402

TABLES = ("sessions", "documents", "reports", "jobs", "chat_messages")


class IsolatedSettings(Settings):
    """断开 backend/.env，保证本脚本不触碰真实 ./data。"""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")


def make_docx(path: Path) -> None:
    from docx import Document

    doc = Document()
    doc.add_heading("方法", level=1)
    paragraph = doc.add_paragraph()
    paragraph.add_run("上传件 + 结构化正文仅在会话内暂存。")
    doc.save(path)


def count_rows(db_path: str, session_id: str) -> dict[str, int]:
    """统计某会话在各表中的残留行数（sessions 表主键为 id，其余为 session_id）。"""
    counts: dict[str, int] = {}
    connection = sqlite3.connect(db_path)
    try:
        for table in TABLES:
            column = "id" if table == "sessions" else "session_id"
            counts[table] = connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (session_id,)
            ).fetchone()[0]
    finally:
        connection.close()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-dir", default="", help="备份目录；提供后额外执行备份验证")
    parser.add_argument("--create-backup", action="store_true", help="实际生成一份 sqlite 快照用于恢复演练")
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="backup_check_"))
    settings = IsolatedSettings(
        db_path=str(tmp / "app.db"),
        temp_dir=str(tmp / "tmp"),
        checklist_dir=str(ROOT / "checklists"),
        app_env="dev",
    )
    set_settings_override(settings)
    failures: list[str] = []
    try:
        init_db(settings.db_path)
        store = Store(settings.db_path)
        session_id, _ = store.create_session(ttl_hours=2)

        sample = tmp / "paper.docx"
        make_docx(sample)
        upload = save_upload(settings.temp_dir, session_id, sample.name, sample.read_bytes(), max_mb=50)
        document_id = store.save_document(session_id, sample.name, '{"source_name":"paper.docx","paragraphs":[]}')
        # 追问历史（需求 15.5.4）：必须与其余会话数据一同被 purge 覆盖
        store.append_chat_message(session_id, "rep_check", "user", "这条该怎么改？", keep=20)
        store.append_chat_message(session_id, "rep_check", "assistant", "补充置信区间。", keep=20)

        before = count_rows(settings.db_path, session_id)
        print("删除传播验证 · 清理前")
        print(f"  会话        : {session_id}")
        print(f"  上传件      : {upload}")
        print(f"  临时文件存在: {upload.exists()}")
        print(f"  数据库行数  : {before}")

        # ---- 备份快照：必须在 purge 之前拍，才能验证「备份保留了 purge 前的数据」 ----
        snapshot: Path | None = None
        if args.backup_dir and args.create_backup:
            backup_dir = Path(args.backup_dir)
            backup_dir.mkdir(parents=True, exist_ok=True)
            snapshot = backup_dir / f"app-backup-{session_id[-8:]}.db"
            source = sqlite3.connect(settings.db_path)
            try:
                destination = sqlite3.connect(str(snapshot))
                source.backup(destination)
                destination.close()
            finally:
                source.close()

        # ---- 删除传播：purge 必须同时覆盖 DB 五张表与临时目录 ----
        purge_session_files(settings.temp_dir, session_id)
        store.purge_session(session_id)

        after = count_rows(settings.db_path, session_id)
        print("删除传播验证 · 清理后")
        print(f"  数据库行数  : {after}")
        print(f"  临时文件存在: {upload.exists()}")

        if any(after[t] for t in TABLES):
            failures.append(f"数据库残留：{ {t: n for t, n in after.items() if n} }")
        if upload.exists():
            failures.append("临时文件未被删除")
        if not document_id:
            failures.append("测试装配失败：未生成 document_id")

        # ---- 备份验证：快照可读、且保留了 purge 前数据（证明备份侧需独立删除传播） ----
        if snapshot is not None:
            readable = sqlite3.connect(str(snapshot))
            try:
                kept = readable.execute("SELECT COUNT(*) FROM sessions WHERE id = ?", (session_id,)).fetchone()[0]
                docs = readable.execute("SELECT COUNT(*) FROM documents WHERE session_id = ?", (session_id,)).fetchone()[0]
            finally:
                readable.close()
            print("备份验证")
            print(f"  快照        : {snapshot} ({snapshot.stat().st_size} bytes)")
            print(f"  快照可读    : True")
            print(f"  快照内会话  : {kept}（purge 前应为 1）")
            print(f"  快照内正文  : {docs}（purge 前应为 1；这正是备份侧必须做删除传播的原因）")
            if kept != 1 or docs != 1:
                failures.append("备份内容不符合预期：purge 前的快照应仍含 1 条会话与其结构化正文")
            print("  结论        : 备份侧需独立执行删除传播；请在上线待办第 4 项中登记备份删除策略")
        elif args.backup_dir:
            print("备份验证：已指定 --backup-dir 但未加 --create-backup，跳过实际备份（演练用）")

        # ---- 隔离自证 ----
        real_data = (ROOT / "data").resolve()
        if real_data.exists() and any(real_data.iterdir()):
            failures.append(f"隔离失效：真实 data/ 被写入 {real_data}")
    finally:
        set_settings_override(None)

    print()
    if failures:
        print("BACKUP CHECK FAIL")
        for item in failures:
            print("  -", item)
        return 1
    print("BACKUP CHECK PASS")
    print(" - 删除传播：sessions/documents/reports/jobs/chat_messages 五张表 + 临时目录均已清空")
    print(" - 隔离：真实 data/ 未被写入")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
