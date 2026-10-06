import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from app.core.errors import AppError
from app.core.ids import new_id
from app.storage.db import connect


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Store:
    """唯一持久化入口：会话、文档、报告、任务。所有按 ID 的读取都强制校验会话归属。"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    # ---- 会话 ----
    def create_session(self, ttl_hours: int) -> tuple[str, str]:
        session_id = new_id("sess")
        token = secrets.token_urlsafe(32)
        now = _now()
        connection = connect(self.db_path)
        try:
            connection.execute(
                "INSERT INTO sessions (id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (session_id, hash_token(token), now.isoformat(), (now + timedelta(hours=ttl_hours)).isoformat()),
            )
            connection.commit()
        finally:
            connection.close()
        return session_id, token

    def get_session_by_token(self, token: str) -> str | None:
        connection = connect(self.db_path)
        try:
            row = connection.execute(
                "SELECT id, expires_at FROM sessions WHERE token_hash = ?", (hash_token(token),)
            ).fetchone()
        finally:
            connection.close()
        if not row:
            return None
        if datetime.fromisoformat(row["expires_at"]) < _now():
            return None
        return row["id"]

    # ---- 文档 ----
    def save_document(self, session_id: str, name: str, ir_json: str) -> str:
        document_id = new_id("doc")
        connection = connect(self.db_path)
        try:
            connection.execute(
                "INSERT INTO documents (id, session_id, name, ir_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (document_id, session_id, name, ir_json, _now().isoformat()),
            )
            connection.commit()
        finally:
            connection.close()
        return document_id

    def authorized_document(self, session_id: str, document_id: str) -> dict:
        return self._authorized("documents", "ir_json", session_id, document_id, kind="document")

    # ---- 报告 ----
    def save_report(self, session_id: str, document_id: str, report_id: str, report_json: str) -> str:
        connection = connect(self.db_path)
        try:
            connection.execute(
                "INSERT INTO reports (id, session_id, document_id, report_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (report_id, session_id, document_id, report_json, _now().isoformat()),
            )
            connection.commit()
        finally:
            connection.close()
        return report_id

    def authorized_report(self, session_id: str, report_id: str) -> dict:
        return self._authorized("reports", "report_json", session_id, report_id, kind="report")

    def report_document_id(self, session_id: str, report_id: str) -> str:
        """取报告对应的 document_id（自由提问需要据此注入全文）。

        越权与不存在统一返回 404，避免泄露资源存在性。
        """
        connection = connect(self.db_path)
        try:
            row = connection.execute(
                "SELECT document_id FROM reports WHERE id = ? AND session_id = ?",
                (report_id, session_id),
            ).fetchone()
        finally:
            connection.close()
        if not row:
            raise AppError("not_found", "report 不存在或无权访问。", 404)
        return str(row["document_id"])

    def list_reports(self, session_id: str) -> list[dict]:
        connection = connect(self.db_path)
        try:
            rows = connection.execute(
                "SELECT id, document_id, report_json, created_at FROM reports WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
        finally:
            connection.close()
        reports = []
        for row in rows:
            payload = json.loads(row["report_json"])
            reports.append(
                {
                    "report_id": row["id"],
                    "document_id": row["document_id"],
                    "document_name": payload.get("document_name"),
                    "counts": payload.get("counts", {}),
                    "created_at": row["created_at"],
                }
            )
        return reports

    # ---- 内部 ----
    def _authorized(self, table: str, column: str, session_id: str, resource_id: str, kind: str) -> dict:
        connection = connect(self.db_path)
        try:
            row = connection.execute(
                f"SELECT {column} FROM {table} WHERE id = ? AND session_id = ?",
                (resource_id, session_id),
            ).fetchone()
        finally:
            connection.close()
        if not row:
            # 越权与不存在统一返回 404，避免泄露资源存在性
            raise AppError("not_found", f"{kind} 不存在或无权访问。", 404)
        return json.loads(row[column])

    # ---- 追问历史 ----
    def append_chat_message(self, session_id: str, report_id: str, role: str, content: str, keep: int) -> None:
        """追加一条追问消息，并把该（会话, 报告）下超出 `keep` 条的最早消息删除。

        `keep` 由 `CHAT_HISTORY_MAX_TURNS` 推导（每轮 user + assistant 两条），
        使落库量随上下文上限一起受约束，避免历史无界增长。
        """
        connection = connect(self.db_path)
        try:
            # 会话可能已被 purge：此时拒绝写入，避免产生永不清理的残留消息
            if connection.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone() is None:
                return
            connection.execute(
                "INSERT INTO chat_messages (id, session_id, report_id, role, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (new_id("msg"), session_id, report_id, role, content, _now().isoformat()),
            )
            connection.execute(
                "DELETE FROM chat_messages WHERE session_id = ? AND report_id = ? AND id NOT IN ("
                "SELECT id FROM chat_messages WHERE session_id = ? AND report_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?"
                ")",
                (session_id, report_id, session_id, report_id, keep),
            )
            connection.commit()
        finally:
            connection.close()

    def list_chat_messages(self, session_id: str, report_id: str) -> list[dict]:
        """按写入顺序返回该（会话, 报告）下的追问消息，供构造多轮上下文。"""
        connection = connect(self.db_path)
        try:
            rows = connection.execute(
                "SELECT role, content FROM chat_messages WHERE session_id = ? AND report_id = ? "
                "ORDER BY created_at ASC, rowid ASC",
                (session_id, report_id),
            ).fetchall()
        finally:
            connection.close()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def purge_session(self, session_id: str) -> None:
        connection = connect(self.db_path)
        try:
            connection.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM reports WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM documents WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM jobs WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            connection.commit()
        finally:
            connection.close()
