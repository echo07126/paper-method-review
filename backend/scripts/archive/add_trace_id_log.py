"""把 DeepSeek 的 x-ds-trace-id 记入审计日志，便于与控制台对账。"""
from pathlib import Path

path = Path(__file__).resolve().parents[2] / "backend" / "app" / "engine" / "llm_provider.py"
text = path.read_text(encoding="utf-8")

old_post = '''    def _post(self, payload: dict) -> dict:
        with self._semaphore:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        return response.json()'''
new_post = '''    def _post(self, payload: dict) -> tuple[dict, str]:
        with self._semaphore:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        return response.json(), response.headers.get("x-ds-trace-id", "-")'''

old_log = '''    def _log_call(self, mode: str, payload: dict, started: float, attempt: int) -> None:
        usage = payload.get("usage", {})
        safe_logger().info(
            "llm_call mode=%s model=%s response_id=%s tokens_in=%s tokens_out=%s duration_ms=%s retries=%s",
            mode,
            self.model,
            payload.get("id"),
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            int((time.monotonic() - started) * 1000),
            attempt,
        )'''
new_log = '''    def _log_call(self, mode: str, payload: dict, trace_id: str, started: float, attempt: int) -> None:
        usage = payload.get("usage", {})
        safe_logger().info(
            "llm_call mode=%s model=%s response_id=%s trace_id=%s tokens_in=%s tokens_out=%s duration_ms=%s retries=%s",
            mode,
            self.model,
            payload.get("id"),
            trace_id,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            int((time.monotonic() - started) * 1000),
            attempt,
        )'''

text = text.replace(old_post, new_post)
text = text.replace(old_log, new_log)
text = text.replace(
    '                payload = self._post({"model": self.model, "messages": messages, "temperature": temperature})\n                self._log_call("text", payload, started, attempt)',
    '                payload, trace_id = self._post({"model": self.model, "messages": messages, "temperature": temperature})\n                self._log_call("text", payload, trace_id, started, attempt)',
)
text = text.replace(
    '''                payload = self._post(
                    {
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        "response_format": {"type": "json_object"},
                    }
                )
                content = payload["choices"][0]["message"]["content"]
                json.loads(content)
                self._log_call("structured", payload, started, attempt)''',
    '''                payload, trace_id = self._post(
                    {
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        "response_format": {"type": "json_object"},
                    }
                )
                content = payload["choices"][0]["message"]["content"]
                json.loads(content)
                self._log_call("structured", payload, trace_id, started, attempt)''',
)
path.write_text(text, encoding="utf-8")
print("已加入 trace_id 日志" if "trace_id" in text else "替换失败")
