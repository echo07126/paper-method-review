import hashlib
import logging
import re

REDACT_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9]{8,})"),
    re.compile(r"(?i)(authorization|api[_-]?key)\s*[:=]\s*\S+"),
]

SENSITIVE_KEYS = {"text", "content", "prompt", "token", "api_key", "authorization"}


def key_fingerprint(secret: str) -> str:
    """密钥指纹：用于日志中标识「当前生效的是哪把 Key」，且不可反推出密钥。

    此前日志直接记密钥尾 6 位——尾字符同样属于密钥材料，落盘即是一次泄漏面。
    改为 sha256 前 8 位：同一把 Key 指纹恒定（可跨日志比对、可确认更换是否生效），
    不同 Key 指纹不同，但日志里不再出现任何密钥字符。
    """
    if not secret:
        return "-"
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8]


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
