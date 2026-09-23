"""契约测试：OpenAPI 响应结构必须被声明，且字段出现在前端源码中。"""
import re
from pathlib import Path

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"

# 前端实际调用的接口 -> 期望响应字段（用于跨端一致性）
CHECKED = {
    ("/api/v1/uploads", "post"),
    ("/api/v1/reviews", "post"),
    ("/api/v1/documents/{document_id}", "get"),
    ("/api/v1/reports", "get"),
    ("/api/v1/reports/{report_id}", "get"),
    ("/api/v1/reports/{report_id}/chat", "post"),
    ("/api/v1/compare", "post"),
}


def resolve(spec: dict, schema: dict) -> dict:
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return spec["components"]["schemas"][name]
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
        return resolve(spec, schema["items"])
    return schema


def frontend_text() -> str:
    chunks = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix in {".ts", ".vue"}:
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def test_every_route_declares_response_model() -> None:
    spec = app.openapi()
    missing = []
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            schema = operation.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema")
            if schema is None:
                continue  # 非 JSON 响应（如 Markdown 导出）
            resolved = resolve(spec, schema)
            if "properties" not in resolved:
                missing.append(f"{method.upper()} {path}")
    assert not missing, f"以下接口未声明可解析的响应结构：{missing}"


def test_frontend_uses_declared_response_fields() -> None:
    spec = app.openapi()
    text = frontend_text()
    problems = []
    for path, method in sorted(CHECKED):
        operation = spec["paths"][path][method]
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        resolved = resolve(spec, schema)
        for field in resolved.get("properties", {}):
            if not re.search(rf"\b{re.escape(field)}\b", text):
                problems.append(f"{method.upper()} {path} -> 前端未使用字段 {field}")
    assert not problems, "前后端字段不一致：" + "; ".join(problems)
