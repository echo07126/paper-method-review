"""应用层安全加固：限流、审计日志、过期清理、页数/压缩炸弹校验、生产配置守卫、CORS 通配符防护。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"

(APP / "core" / "ratelimit.py").write_text('''"""极简进程内限流（滑动窗口），用于保护上传与审查等重接口。"""
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AppError

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
    if path.endswith("/reviews"):
        return "reviews", settings.rate_limit_reviews_per_minute
    if path.endswith("/chat"):
        return "chat", settings.rate_limit_reads_per_minute
    return None


def enforce(request: Request) -> None:
    rule = classify(request.url.path)
    if not rule:
        return
    name, limit = rule
    session = request.cookies.get("pm_session", "anonymous")
    client = request.client.host if request.client else "unknown"
    for bucket in (f"{name}:{session}", f"{name}:ip:{client}"):
        if not _hit(bucket, limit):
            raise AppError("rate_limited", "请求过于频繁，请稍后重试。", 429)
''', encoding="utf-8")

(APP / "core" / "audit.py").write_text('''"""审计日志：只记录事件与元数据，不记录论文内容。"""
from app.core.logging import safe_logger

AUDIT_EVENTS = {"session_purge", "report_export", "review_created", "startup_cleanup"}


def audit(event: str, **fields) -> None:
    if event not in AUDIT_EVENTS:
        return
    payload = " ".join(f"{key}={value}" for key, value in sorted(fields.items()))
    safe_logger().info("audit event=%s %s", event, payload)
''', encoding="utf-8")

(APP / "storage" / "maintenance.py").write_text('''"""维护任务：清理过期会话与其临时文件（数据生命周期落地）。"""
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.core.audit import audit
from app.core.logging import safe_logger
from app.storage.db import connect


def cleanup_expired(db_path: str, temp_dir: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    removed_sessions = 0
    removed_dirs = 0
    connection = connect(db_path)
    try:
        rows = connection.execute("SELECT id FROM sessions WHERE expires_at < ?", (now,)).fetchall()
        session_ids = [row["id"] for row in rows]
        for session_id in session_ids:
            connection.execute("DELETE FROM reports WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM documents WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM jobs WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        connection.commit()
        removed_sessions = len(session_ids)
    finally:
        connection.close()

    root = Path(temp_dir)
    known = set()
    connection = connect(db_path)
    try:
        known = {row["id"] for row in connection.execute("SELECT id FROM sessions").fetchall()}
    finally:
        connection.close()
    if root.exists():
        for directory in root.iterdir():
            if directory.is_dir() and directory.name not in known:
                shutil.rmtree(directory, ignore_errors=True)
                removed_dirs += 1

    result = {"removed_sessions": removed_sessions, "removed_temp_dirs": removed_dirs}
    safe_logger().info("maintenance cleanup done %s", result)
    audit("startup_cleanup", removed_sessions=removed_sessions, removed_temp_dirs=removed_dirs)
    return result
''', encoding="utf-8")

# config：限流参数 + CORS 通配符与生产配置守卫
config_path = APP / "core" / "config.py"
text = config_path.read_text(encoding="utf-8")
if "rate_limit_uploads_per_minute" not in text:
    text = text.replace(
        "    demote_on_figures: bool = False",
        "    demote_on_figures: bool = False\n"
        "    rate_limit_uploads_per_minute: int = 20\n"
        "    rate_limit_reviews_per_minute: int = 10\n"
        "    rate_limit_reads_per_minute: int = 120",
    )
if "def guard_production" not in text:
    text = text.replace(
        "    def require_llm(self) -> None:",
        '''    def guard_production(self) -> list[str]:
        """生产配置守卫：返回告警列表；出现严重配置（prod 下开 debug/docs）时抛错。"""
        problems: list[str] = []
        if "*" in self.origins:
            problems.append("ALLOWED_ORIGINS 不能包含通配符 *（与凭据 Cookie 同用不安全）")
        if self.app_env != "dev":
            if self.debug:
                problems.append("生产环境必须关闭 DEBUG")
            if self.docs_enabled:
                problems.append("生产环境必须关闭或保护 API Docs")
        if problems:
            raise RuntimeError("配置不合规：" + "；".join(problems))
        return problems

    def require_llm(self) -> None:''',
    )
config_path.write_text(text, encoding="utf-8")

# validators：DOCX 容器级校验（页数 + 压缩炸弹）
validators = APP / "validators.py"
text = validators.read_text(encoding="utf-8")
if "validate_docx_container" not in text:
    text += '''

MAX_UNCOMPRESSED_MB = 300
MAX_COMPRESSION_RATIO = 120


def validate_docx_container(path, max_pages: int, max_uncompressed_mb: int = MAX_UNCOMPRESSED_MB) -> dict:
    """DOCX 容器级安全校验：解压体积（压缩炸弹）与页数上限。"""
    import zipfile

    info = {"uncompressed_mb": 0.0, "pages": None}
    try:
        with zipfile.ZipFile(path) as archive:
            total = sum(item.file_size for item in archive.infolist())
            info["uncompressed_mb"] = round(total / 1024 / 1024, 2)
            compressed = max(sum(item.compress_size for item in archive.infolist()), 1)
            if total > max_uncompressed_mb * 1024 * 1024 or total / compressed > MAX_COMPRESSION_RATIO:
                raise AppError("file_too_large_uncompressed", "文档解压后体积异常，已拒绝处理。", 413)
            if "docProps/app.xml" in archive.namelist():
                import re

                xml = archive.read("docProps/app.xml").decode("utf-8", errors="ignore")
                match = re.search(r"<Pages>(\\d+)</Pages>", xml)
                if match:
                    info["pages"] = int(match.group(1))
    except zipfile.BadZipFile as exc:
        raise AppError("file_corrupted", "文件不是有效的 DOCX（压缩包损坏）。", 400) from exc

    if info["pages"] and max_pages and info["pages"] > max_pages:
        raise AppError("too_many_pages", f"文档页数 {info['pages']} 超过上限 {max_pages} 页。", 413)
    return info
'''
validators.write_text(text, encoding="utf-8")

# files.py：落盘后执行容器校验
files = APP / "storage" / "files.py"
text = files.read_text(encoding="utf-8")
text = text.replace("from app.validators import validate_upload", "from app.core.config import get_settings\nfrom app.validators import validate_docx_container, validate_upload")
text = text.replace(
    "    path.write_bytes(content)\n    return path",
    "    path.write_bytes(content)\n"
    "    settings = get_settings()\n"
    "    validate_docx_container(path, settings.max_pages)\n"
    "    return path",
)
files.write_text(text, encoding="utf-8")

# main.py：启动守卫 + 清理 + 限流中间件 + CORS credentials
main = APP / "main.py"
text = main.read_text(encoding="utf-8")
text = text.replace("from app.core.logging import setup_logging", "from app.core.config import get_settings as _get_settings\nfrom app.core.logging import setup_logging\nfrom app.core.ratelimit import enforce as enforce_rate_limit\nfrom app.storage.maintenance import cleanup_expired")
text = text.replace(
    "    init_db(settings.db_path)\n    os.makedirs(settings.temp_dir, exist_ok=True)\n    yield",
    "    settings.guard_production()\n"
    "    init_db(settings.db_path)\n"
    "    os.makedirs(settings.temp_dir, exist_ok=True)\n"
    "    cleanup_expired(settings.db_path, settings.temp_dir)\n"
    "    yield",
)
text = text.replace(
    "        allow_credentials=True,",
    '        allow_credentials="*" not in settings.origins,',
)
text = text.replace(
    "        request.state.request_id = uuid.uuid4().hex[:12]\n        response = await call_next(request)",
    "        request.state.request_id = uuid.uuid4().hex[:12]\n        enforce_rate_limit(request)\n        response = await call_next(request)",
)
main.write_text(text, encoding="utf-8")

# 审计：purge / export / review
session_route = APP / "api" / "routes_session.py"
text = session_route.read_text(encoding="utf-8")
text = text.replace("from app.api.deps import SESSION_COOKIE, get_store, resolve_session", "from app.api.deps import SESSION_COOKIE, get_store, resolve_session\nfrom app.core.audit import audit")
text = text.replace('    response.delete_cookie(SESSION_COOKIE)\n    return {"status": "purged"}', '    response.delete_cookie(SESSION_COOKIE)\n    audit("session_purge", session_id=session_id)\n    return {"status": "purged"}')
session_route.write_text(text, encoding="utf-8")

report_route = APP / "api" / "routes_report.py"
text = report_route.read_text(encoding="utf-8")
text = text.replace("from app.api.deps import get_store, resolve_session", "from app.api.deps import get_store, resolve_session\nfrom app.core.audit import audit")
text = text.replace('    if format != "markdown":', '    audit("report_export", report_id=report_id, format=format)\n    if format != "markdown":')
report_route.write_text(text, encoding="utf-8")

review_route = APP / "api" / "routes_review.py"
text = review_route.read_text(encoding="utf-8")
text = text.replace("from app.api.deps import get_store, resolve_session", "from app.api.deps import get_store, resolve_session\nfrom app.core.audit import audit")
text = text.replace('    return {\n        "report_id": report.report_id,', '    audit("review_created", report_id=report.report_id, problems=report.counts.get("total", 0), use_llm=payload.use_llm)\n    return {\n        "report_id": report.report_id,')
review_route.write_text(text, encoding="utf-8")

print("应用层加固完成")
