"""为每次模型调用写审计日志（response_id + tokens + 耗时），便于与 DeepSeek 控制台对账。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
provider = ROOT / "backend" / "app" / "engine" / "llm_provider.py"
text = provider.read_text(encoding="utf-8")

if "llm_call" not in text:
    text = text.replace(
        "import httpx\n",
        "import httpx\n\nfrom app.core.logging import safe_logger\n",
        1,
    )

    # 结构化调用
    text = text.replace(
        """                usage = payload.get("usage", {})
                return LLMResult(
                    content=payload["choices"][0]["message"]["content"],""",
        """                usage = payload.get("usage", {})
                safe_logger().info(
                    "llm_call mode=structured model=%s response_id=%s tokens_in=%s tokens_out=%s duration_ms=%s retries=%s",
                    self.model,
                    payload.get("id"),
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    int((time.monotonic() - started) * 1000),
                    attempt,
                )
                return LLMResult(
                    content=payload["choices"][0]["message"]["content"],""",
    )

    # 自由文本调用
    text = text.replace(
        """                payload = response.json()
                usage = payload.get("usage", {})
                return LLMResult(
                    content=payload["choices"][0]["message"]["content"],
                    model=self.model,""",
        """                payload = response.json()
                usage = payload.get("usage", {})
                safe_logger().info(
                    "llm_call mode=text model=%s response_id=%s tokens_in=%s tokens_out=%s duration_ms=%s retries=%s",
                    self.model,
                    payload.get("id"),
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    int((time.monotonic() - started) * 1000),
                    attempt,
                )
                return LLMResult(
                    content=payload["choices"][0]["message"]["content"],
                    model=self.model,""",
    )
    provider.write_text(text, encoding="utf-8")
    print("已加入 llm_call 审计日志")
else:
    print("已存在 llm_call 日志，跳过")
