"""从后端 OpenAPI 生成接口文档（含人工核对的响应字段约定），保证文档与实现同步。

OpenAPI 来源优先取运行中的后端（`/openapi.json`，即真实部署形态）；连不上时退回
进程内 `create_app().openapi()`，使文档生成不依赖「先起服务」这一步。
"""
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
OUTPUT = ROOT / "docs" / "engineering" / "API接口说明.md"
OPENAPI_URL = "http://127.0.0.1:8000/openapi.json"

PURPOSE = {
    "/api/v1/health": "健康检查（存活与配置状态）",
    "/api/v1/uploads": "上传 DOCX 并解析",
    "/api/v1/documents/{document_id}": "读取解析结果（章节/段落/表格，供报告页原文预览）",
    "/api/v1/reviews": "提交结构化审查任务（202 返回 task_id，轮询 /api/v1/tasks/{task_id}）",
    "/api/v1/reports": "列出当前会话的报告（供修改对比选择）",
    "/api/v1/reports/{report_id}": "读取单份报告全文（findings 含锚点）",
    "/api/v1/reports/{report_id}/export": "导出报告（format=markdown）",
    "/api/v1/reports/{report_id}/chat": "提交报告问答任务（scope=finding 追问单条 / scope=fulltext 全文自由提问；202 返回 task_id，轮询 /tasks/{task_id}）",
    "/api/v1/reports/{report_id}/revision": "提交生成修改稿任务（按报告问题生成修改稿并二次审查；202 返回 task_id，轮询 /tasks/{task_id}）",
    "/api/v1/compare": "提交修改前后对比任务（两份 report_id，或自动生成修改稿；202 返回 task_id，轮询 /tasks/{task_id}）",
    "/api/v1/tasks/{task_id}": "查询任务状态与结果（queued/running/succeeded/failed；succeeded 时 result 即旧同步响应体）",
    "/api/v1/sessions/purge": "删除当前会话数据（数据库 + 临时文件）",
}

# 响应字段约定：仅作为无 JSON 结构接口（如 Markdown 导出）的补充说明；
# 声明了 response_model 的接口（含任务化后的 202/TaskAccepted）由 OpenAPI 自动生成。
RESPONSE_FIELDS = {
    "/api/v1/health": "status, app_env, docs_enabled",
    "/api/v1/uploads": "document_id, parser, sections[], paragraph_count, citation_count, reference_count, warnings[]",
    "/api/v1/documents/{document_id}": "document_id, source_name, sections[], paragraphs[], tables[], warnings[], parser",
    "/api/v1/reviews": "任务 result（同旧同步响应体）：report_id, counts{}, duration_ms, tokens{}, notes[], figure_references, demote_on_figures",
    "/api/v1/reports": "[{report_id, document_id, document_name, counts{}, created_at}]",
    "/api/v1/reports/{report_id}": "report_id, document_name, checklist_version, findings[], counts{}, duration_ms, tokens{}, notes[], figure_references, demote_on_figures",
    "/api/v1/reports/{report_id}/export": "Markdown 文本（PlainTextResponse）",
    "/api/v1/reports/{report_id}/chat": "任务 result（同旧同步响应体）：answer, source(llm|fallback), tokens?, note?, session_id, history[], truncated, scope",
    "/api/v1/reports/{report_id}/revision": "任务 result：修改稿二次审查报告 report_id, document_id, document_name, findings[], counts{}, notes[], tokens{}",
    "/api/v1/compare": "任务 result（同旧同步响应体）：before{}, after{}, resolved[], new[], kept[], before_findings[], after_findings[], resolved_findings[], new_findings[], kept_findings[], document_id?（每条 finding 另含 revision_status: rewritten|manual|pending 与 revision_note）",
    "/api/v1/tasks/{task_id}": "task_id, kind, state, result?, error?, created_at, updated_at",
    "/api/v1/sessions/purge": "status",
}


def resolve(spec: dict, schema: dict) -> dict:
    if not isinstance(schema, dict):
        return {}
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return spec.get("components", {}).get("schemas", {}).get(name, {})
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
        resolved = resolve(spec, schema["items"])
        return {**resolved, "_is_array": True}
    return schema


def fields(spec: dict, schema: dict, limit: int = 8) -> str:
    schema = resolve(spec, schema)
    props = list(schema.get("properties", {}).keys())
    if not props:
        return "—"
    text = ", ".join(props[:limit]) + ("…" if len(props) > limit else "")
    return f"[{text}]" if schema.get("_is_array") else text


def load_spec() -> tuple[dict, str]:
    """取 OpenAPI 文档，返回 (spec, 来源说明)。

    先读运行中的后端（能反映真实部署的路由与中间件）；不可用时退回进程内
    `create_app().openapi()`——路由与 `response_model` 完全一致，只是少了实际网络形态。
    这样在 CI 或本地未起服务时也能重新生成文档，不会留下过期文档。
    """
    try:
        response = httpx.get(OPENAPI_URL, timeout=5)
        response.raise_for_status()
        return response.json(), f"运行中的后端 `{OPENAPI_URL}`"
    except Exception as exc:  # noqa: BLE001 - 未起服务是常见情况，退回复退路径
        if str(BACKEND) not in sys.path:
            sys.path.insert(0, str(BACKEND))
        from app.main import create_app

        return create_app().openapi(), f"进程内 `create_app().openapi()`（未连上 {OPENAPI_URL}：{exc}）"


def main() -> int:
    spec, source = load_spec()
    lines = [
        "# API 接口说明（与后端实现同步）",
        "",
        "> 生成方式：`python backend/scripts/gen_api_doc.py`（读取 OpenAPI，并附人工核对的响应字段）。",
        f"> 本次来源：{source}。",
        "> 修改接口后请重新生成；交互式文档见 `http://127.0.0.1:8000/docs`。",
        "",
        "## 1. 接口清单（OpenAPI 自动生成）",
        "",
        "| 方法 | 路径 | 用途 | 关键请求字段 | 关键响应字段 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for path, methods in sorted(spec.get("paths", {}).items()):
        for method, operation in methods.items():
            request_fields = "—"
            content = operation.get("requestBody", {}).get("content", {})
            if "application/json" in content:
                request_fields = fields(spec, content["application/json"].get("schema", {}))
            elif "multipart/form-data" in content:
                request_fields = "file (DOCX)"
            params = [p["name"] for p in operation.get("parameters", [])]
            if params:
                prefix = "" if request_fields == "—" else request_fields + "; "
                request_fields = prefix + "path/query: " + ", ".join(params)
            response_schema = None
            for code in ("200", "202"):
                response_schema = operation.get("responses", {}).get(code, {}).get("content", {}).get("application/json", {}).get("schema")
                if response_schema:
                    break
            response_fields = fields(spec, response_schema) if response_schema else RESPONSE_FIELDS.get(path, "text")
            lines.append(f"| {method.upper()} | `{path}` | {PURPOSE.get(path, '')} | {request_fields} | {response_fields} |")

    lines += ["", "## 2. 说明", "- 第 1 节的“关键响应字段”直接来自 OpenAPI（各接口已声明 `response_model`）。",
              "- `RESPONSE_FIELDS` 仅作为无 JSON 结构接口（如 Markdown 导出）的补充说明。"]

    lines += [
        "",
        "## 3. 约定",
        "- 统一前缀 `/api/v1`；会话通过 HttpOnly Cookie（`pm_session`）维护，免登录。",
        "- 错误响应统一为 `{code, message, request_id}`；跨会话访问他人资源返回 404。",
        "- 审查参数：`use_llm`（是否启用模型顾问，**不传则用服务端默认 `LLM_DEFAULT_ENABLED=true`，即默认启用**）、`demote_on_figures`（图表未解析时是否保守降级，不传则用服务端默认）。",
        "- 追问上下文：`history` 为客户端可选的 `[{role, content}]`（服务端仅在落库历史为空时采用）；上限 `CHAT_HISTORY_MAX_TURNS=10`（即 20 条消息）与 `CHAT_HISTORY_MAX_CHARS=8000`（含 system），超出时**整轮截断**并置 `truncated=true`。",
        "- 报告问答作用域：`scope=finding`（追问，注入单条问题上下文）与 `scope=fulltext`（自由提问，注入全文 DATA 区，`QA_FULLTEXT_MAX_CHARS=12000`）；两者共用同一轮数与字符上限。",
        "- 对比参数：`use_llm`（是否用模型结合全文生成修改稿补写，不传则用服务端默认；关闭则退回清单规范句式）；未提供 `after_report_id` 时后端自动生成修改稿并二次审查。",
        "- 任务模式：四个重接口（`/reviews`、`/compare`、`/reports/{id}/chat`、`/reports/{id}/revision`）均**立即返回 202** 与 `{task_id, state, kind, poll_url}`，业务主体在受控线程池执行；前端轮询 `GET /api/v1/tasks/{task_id}`，`state=succeeded` 时 `result` 即旧同步响应体、`state=failed` 时 `error` 带 `code/message`。`TASK_MAX_WORKERS=2` 控制并发上限，`TASK_RETENTION_MINUTES=30` 控制终态/僵尸任务保留期。",
        "",
        "## 4. 已知缺口",
        "- 已解决：全部接口声明 `response_model`，OpenAPI 含响应结构；`tests/test_api_contract.py` 做前后端字段契约校验（含任务 result 字段）。",
    ]
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
