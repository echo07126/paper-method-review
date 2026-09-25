"""从运行中的后端 OpenAPI 生成接口文档（含人工核对的响应字段约定），保证文档与实现同步。"""
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs" / "engineering" / "API接口说明.md"

PURPOSE = {
    "/api/v1/health": "健康检查（存活与配置状态）",
    "/api/v1/uploads": "上传 DOCX 并解析",
    "/api/v1/documents/{document_id}": "读取解析结果（章节/段落/表格，供报告页原文预览）",
    "/api/v1/reviews": "执行结构化审查（可选 use_llm / demote_on_figures）",
    "/api/v1/reports": "列出当前会话的报告（供修改对比选择）",
    "/api/v1/reports/{report_id}": "读取单份报告全文（findings 含锚点）",
    "/api/v1/reports/{report_id}/export": "导出报告（format=markdown）",
    "/api/v1/reports/{report_id}/chat": "报告问答（scope=finding 追问单条 / scope=fulltext 全文自由提问；有 Key 走模型，无 Key 模板降级）",
    "/api/v1/reports/{report_id}/revision": "按报告问题生成修改稿并二次审查（模型结合全文补写、校验原文出处）",
    "/api/v1/compare": "修改前后对比（两份 report_id）",
    "/api/v1/sessions/purge": "删除当前会话数据（数据库 + 临时文件）",
}

# 响应字段约定：与 routes_*.py 实现核对（当前 FastAPI 未声明 response_model，故人工记录）
RESPONSE_FIELDS = {
    "/api/v1/health": "status, app_env, docs_enabled",
    "/api/v1/uploads": "document_id, parser, sections[], paragraph_count, citation_count, reference_count, warnings[]",
    "/api/v1/documents/{document_id}": "document_id, source_name, sections[], paragraphs[], tables[], warnings[], parser",
    "/api/v1/reviews": "report_id, counts{}, duration_ms, tokens{}, notes[], figure_references, demote_on_figures",
    "/api/v1/reports": "[{report_id, document_id, document_name, counts{}, created_at}]",
    "/api/v1/reports/{report_id}": "report_id, document_name, checklist_version, findings[], counts{}, duration_ms, tokens{}, notes[], figure_references, demote_on_figures",
    "/api/v1/reports/{report_id}/export": "Markdown 文本（PlainTextResponse）",
    "/api/v1/reports/{report_id}/chat": "answer, source(llm|fallback), tokens?(llm), note?(fallback), session_id, history[], truncated, scope",
    "/api/v1/reports/{report_id}/revision": "report_id, document_name, findings[], counts{}, notes[], tokens{}（修改稿二次审查报告）",
    "/api/v1/compare": "before{}, after{}, resolved[], new[], kept[], before_findings[], after_findings[], resolved_findings[]",
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


def main() -> int:
    spec = httpx.get("http://127.0.0.1:8000/openapi.json", timeout=10).json()
    lines = [
        "# API 接口说明（与后端实现同步）",
        "",
        "> 生成方式：`python backend/scripts/gen_api_doc.py`（从运行中的后端读取 `/openapi.json`，并附人工核对的响应字段）。",
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
            response_schema = operation.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema")
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
        "",
        "## 4. 已知缺口",
        "- 已解决：全部接口声明 `response_model`，OpenAPI 含响应结构；`tests/test_api_contract.py` 做前后端字段契约校验。",
    ]
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
