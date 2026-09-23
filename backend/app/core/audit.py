"""审计日志：只记录事件与元数据，不记录论文内容。"""
from app.core.logging import safe_logger

AUDIT_EVENTS = {"session_purge", "report_export", "review_created", "startup_cleanup"}


def audit(event: str, **fields) -> None:
    if event not in AUDIT_EVENTS:
        return
    payload = " ".join(f"{key}={value}" for key, value in sorted(fields.items()))
    safe_logger().info("audit event=%s %s", event, payload)
