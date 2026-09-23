"""审计日志记录本次使用的 Key 尾号，便于确认到底用了哪把 Key。"""
from pathlib import Path

path = Path(__file__).resolve().parents[2] / "backend" / "app" / "engine" / "llm_provider.py"
text = path.read_text(encoding="utf-8")
old = '''        safe_logger().info(
            "llm_call mode=%s model=%s response_id=%s trace_id=%s tokens_in=%s tokens_out=%s duration_ms=%s retries=%s",
            mode,
            self.model,
            payload.get("id"),
            trace_id,'''
new = '''        safe_logger().info(
            "llm_call mode=%s model=%s key_tail=%s response_id=%s trace_id=%s tokens_in=%s tokens_out=%s duration_ms=%s retries=%s",
            mode,
            self.model,
            self.api_key[-6:],
            payload.get("id"),
            trace_id,'''
if old in text:
    path.write_text(text.replace(old, new), encoding="utf-8")
    print("日志已记录 key_tail")
else:
    print("[warn] 未找到日志锚点")
