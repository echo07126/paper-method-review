import json
import threading
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.core.logging import safe_logger


class LLMUnavailable(RuntimeError):
    pass


@dataclass
class LLMResult:
    content: str
    model: str
    tokens: dict[str, int] = field(default_factory=dict)
    retries: int = 0
    duration_ms: int = 0


class LLMProvider(Protocol):
    def complete_structured(
        self, messages: list[dict], temperature: float = 0.0, max_tokens: int | None = None
    ) -> LLMResult: ...

    def complete_text(
        self, messages: list[dict], temperature: float = 0.3, max_tokens: int | None = None
    ) -> LLMResult: ...


class DeepSeekProvider:
    """DeepSeek（OpenAI 兼容）。含超时、重试、并发限制与审计日志（不记录内容）。"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int = 60,
        max_retries: int = 3,
        max_concurrency: int = 2,
    ) -> None:
        if not api_key:
            raise LLMUnavailable("未配置 DEEPSEEK_API_KEY，无法进行模型判定。")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._semaphore = threading.BoundedSemaphore(max_concurrency)

    def _post(self, payload: dict) -> tuple[dict, str]:
        with self._semaphore:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        return response.json(), response.headers.get("x-ds-trace-id", "-")

    def _log_call(self, mode: str, payload: dict, trace_id: str, started: float, attempt: int) -> None:
        usage = payload.get("usage", {})
        safe_logger().info(
            "llm_call mode=%s model=%s key_tail=%s response_id=%s trace_id=%s tokens_in=%s tokens_out=%s duration_ms=%s retries=%s",
            mode,
            self.model,
            self.api_key[-6:],
            payload.get("id"),
            trace_id,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            int((time.monotonic() - started) * 1000),
            attempt,
        )

    def complete_text(
        self, messages: list[dict], temperature: float = 0.3, max_tokens: int | None = None
    ) -> LLMResult:
        """自由文本调用（不含 JSON 约束），用于追问答疑等自然语言场景。"""
        started = time.monotonic()
        last_error: Exception | None = None
        request: dict = {"model": self.model, "messages": messages, "temperature": temperature}
        if max_tokens:
            request["max_tokens"] = max_tokens
        for attempt in range(self.max_retries + 1):
            try:
                payload, trace_id = self._post(request)
                self._log_call("text", payload, trace_id, started, attempt)
                usage = payload.get("usage", {})
                return LLMResult(
                    content=payload["choices"][0]["message"]["content"],
                    model=self.model,
                    tokens={
                        "input": int(usage.get("prompt_tokens", 0)),
                        "output": int(usage.get("completion_tokens", 0)),
                    },
                    retries=attempt,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 8))
        raise LLMUnavailable(f"模型调用失败（已重试 {self.max_retries} 次）：{last_error}")

    def complete_structured(
        self, messages: list[dict], temperature: float = 0.0, max_tokens: int | None = None
    ) -> LLMResult:
        """结构化 JSON 调用：要求返回合法 JSON，否则重试。"""
        started = time.monotonic()
        last_error: Exception | None = None
        request: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        if max_tokens:
            request["max_tokens"] = max_tokens
        for attempt in range(self.max_retries + 1):
            try:
                payload, trace_id = self._post(request)
                content = payload["choices"][0]["message"]["content"]
                json.loads(content)
                self._log_call("structured", payload, trace_id, started, attempt)
                usage = payload.get("usage", {})
                return LLMResult(
                    content=content,
                    model=self.model,
                    tokens={
                        "input": int(usage.get("prompt_tokens", 0)),
                        "output": int(usage.get("completion_tokens", 0)),
                    },
                    retries=attempt,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 8))
        raise LLMUnavailable(f"模型调用失败（已重试 {self.max_retries} 次）：{last_error}")


def build_provider(settings) -> LLMProvider | None:
    try:
        return DeepSeekProvider(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            max_concurrency=settings.llm_max_concurrency,
        )
    except LLMUnavailable:
        return None
