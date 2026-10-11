"""契约测试：OpenAPI 响应结构必须被声明，且字段出现在前端源码中。"""
import re
from pathlib import Path

from app.main import app
from app.models.schemas import ChatResponse, CompareResponse, ReviewCreateResponse

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
    ("/api/v1/tasks/{task_id}", "get"),
}

# 任务 kind -> 旧同步响应模型：入队后 result 必须仍承载这些字段（前端下游逻辑零改动）
RESULT_MODELS = {
    "review": ReviewCreateResponse,
    "compare": CompareResponse,
    "chat": ChatResponse,
}


def _response_schema(operation: dict) -> dict | None:
    """取操作声明的 JSON 响应结构，兼容同步 200 与任务化后的 202。"""
    responses = operation.get("responses", {})
    for code in ("200", "202"):
        content = responses.get(code, {}).get("content", {}).get("application/json", {})
        if "schema" in content:
            return content["schema"]
    return None


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
            schema = _response_schema(operation)
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
        schema = _response_schema(operation)
        assert schema is not None, f"{method.upper()} {path} 未声明 JSON 响应结构"
        resolved = resolve(spec, schema)
        for field in resolved.get("properties", {}):
            if not re.search(rf"\b{re.escape(field)}\b", text):
                problems.append(f"{method.upper()} {path} -> 前端未使用字段 {field}")
    assert not problems, "前后端字段不一致：" + "; ".join(problems)


def test_task_result_models_stay_used_by_frontend() -> None:
    """任务化不降低契约强度：POST 返回 202/TaskAccepted，但 result 仍承载旧响应模型字段。"""
    text = frontend_text()
    problems = []
    for kind, model in RESULT_MODELS.items():
        fields = list(model.model_fields)
        assert fields, f"{model.__name__} 未声明任何字段"
        for field in fields:
            if not re.search(rf"\b{re.escape(field)}\b", text):
                problems.append(f"{kind}.result -> {model.__name__}.{field} 前端未使用")
    assert not problems, "任务 result 字段与前端不一致：" + "; ".join(problems)
