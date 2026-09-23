"""连通性检查：验证 DeepSeek Key / 模型可用性（不打印密钥）。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import httpx  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.engine.llm_provider import DeepSeekProvider, LLMUnavailable  # noqa: E402


def main() -> int:
    settings = get_settings()
    if not settings.deepseek_api_key:
        print("FAIL: 未读取到 DEEPSEEK_API_KEY（检查 backend/.env）")
        return 2
    print(f"key loaded: {'*' * 6}{settings.deepseek_api_key[-4:]}  base_url={settings.deepseek_base_url}")

    try:
        response = httpx.get(
            f"{settings.deepseek_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            timeout=30,
        )
        print("models status:", response.status_code)
        if response.status_code == 200:
            models = [m.get("id") for m in response.json().get("data", [])]
            print("available models:", ", ".join(models) if models else "(empty)")
    except httpx.HTTPError as exc:
        print("models request failed:", type(exc).__name__, exc)

    provider = DeepSeekProvider(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=1,
        max_concurrency=1,
    )
    try:
        result = provider.complete_structured(
            [
                {"role": "system", "content": "你只输出 JSON。"},
                {"role": "user", "content": '请输出 JSON：{"ok": true, "model": "deepseek"}'},
            ]
        )
        parsed = json.loads(result.content)
        print("chat call OK  model=", result.model, " tokens=", result.tokens, " duration_ms=", result.duration_ms)
        print("response:", parsed)
        print("LLM CHECK PASS")
        return 0
    except LLMUnavailable as exc:
        print("LLM CHECK FAIL:", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
