# API 接口说明（与后端实现同步）

> 生成方式：`python backend/scripts/gen_api_doc.py`（从运行中的后端读取 `/openapi.json`，并附人工核对的响应字段）。
> 修改接口后请重新生成；交互式文档见 `http://127.0.0.1:8000/docs`。

## 1. 接口清单（OpenAPI 自动生成）

| 方法 | 路径 | 用途 | 关键请求字段 | 关键响应字段 |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/compare` | 修改前后对比（两份 report_id） | before_report_id, after_report_id | before, after, resolved, new, kept |
| GET | `/api/v1/documents/{document_id}` | 读取解析结果（章节/段落/表格，供报告页原文预览） | path/query: document_id | document_id, source_name, sections, paragraphs, tables, warnings, parser |
| GET | `/api/v1/health` | 健康检查（存活与配置状态） | — | status, app_env, docs_enabled |
| GET | `/api/v1/reports` | 列出当前会话的报告（供修改对比选择） | — | [report_id, document_id, document_name, counts, created_at] |
| GET | `/api/v1/reports/{report_id}` | 读取单份报告全文（findings 含锚点） | path/query: report_id | report_id, document_name, checklist_version, findings, counts, duration_ms, tokens, notes… |
| POST | `/api/v1/reports/{report_id}/chat` | 针对报告追问（多轮上下文；有 Key 走模型，无 Key 模板降级） | question, finding_id, history; path/query: report_id | answer, source, tokens, note, session_id, history, truncated |
| GET | `/api/v1/reports/{report_id}/export` | 导出报告（format=markdown） | path/query: report_id, format | Markdown 文本（PlainTextResponse） |
| POST | `/api/v1/reviews` | 执行结构化审查（可选 use_llm / demote_on_figures） | document_id, use_llm, demote_on_figures | report_id, counts, duration_ms, tokens, notes, figure_references, demote_on_figures, paper_type |
| POST | `/api/v1/sessions/purge` | 删除当前会话数据（数据库 + 临时文件） | — | status |
| POST | `/api/v1/uploads` | 上传 DOCX 并解析 | file (DOCX) | document_id, parser, sections, paragraph_count, citation_count, reference_count, warnings |

## 2. 说明
- 第 1 节的“关键响应字段”直接来自 OpenAPI（各接口已声明 `response_model`）。
- `RESPONSE_FIELDS` 仅作为无 JSON 结构接口（如 Markdown 导出）的补充说明。

## 3. 约定
- 统一前缀 `/api/v1`；会话通过 HttpOnly Cookie（`pm_session`）维护，免登录。
- 错误响应统一为 `{code, message, request_id}`；跨会话访问他人资源返回 404。
- 审查参数：`use_llm`（是否启用模型顾问，**不传则用服务端默认 `LLM_DEFAULT_ENABLED=true`，即默认启用**）、`demote_on_figures`（图表未解析时是否保守降级，不传则用服务端默认）。
- 追问上下文：`history` 为客户端可选的 `[{role, content}]`（服务端仅在落库历史为空时采用）；上限 `CHAT_HISTORY_MAX_TURNS=10`（即 20 条消息）与 `CHAT_HISTORY_MAX_CHARS=8000`（含 system），超出时**整轮截断**并置 `truncated=true`。

## 4. 已知缺口
- 已解决：全部接口声明 `response_model`，OpenAPI 含响应结构；`tests/test_api_contract.py` 做前后端字段契约校验。
