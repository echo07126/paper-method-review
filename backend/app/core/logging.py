import logging
import re

REDACT_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9]{8,})"),
    re.compile(r"(?i)(authorization|api[_-]?key)\s*[:=]\s*\S+"),
]

SENSITIVE_KEYS = {"text", "content", "prompt", "token", "api_key", "authorization"}


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # 先按键剔除：以字典形式传入的 text/content/prompt 等字段一律置为 [REDACTED]，
        # 避免论文正文或密钥随结构化日志落盘。
        if isinstance(record.args, dict) and SENSITIVE_KEYS & set(record.args):
            record.args = {
                key: ("[REDACTED]" if key in SENSITIVE_KEYS else value) for key, value in record.args.items()
            }
        message = record.getMessage()
        for pattern in REDACT_PATTERNS:
            message = pattern.sub("[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("app")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        handler.addFilter(RedactionFilter())
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def safe_logger() -> logging.Logger:
    return logging.getLogger("app")
