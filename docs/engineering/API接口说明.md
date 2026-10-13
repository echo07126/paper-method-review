# API 接口说明（与后端实现同步）

> 生成方式：`python backend/scripts/gen_api_doc.py`（读取 OpenAPI，并附人工核对的响应字段）。
> 本次来源：进程内 `create_app().openapi()`（未连上 http://127.0.0.1:8000/openapi.json：[WinError 10061] 由于目标计算机积极拒绝，无法连接。）。
> 修改接口后请重新生成；交互式文档见 `http://127.0.0.1:8000/docs`。

## 1. 接口清单（OpenAPI 自动生成）

| 方法 | 路径 | 用途 | 关键请求字段 | 关键响应字段 |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/compare` | 提交修改前后对比任务（两份 report_id，或自动生成修改稿；202 返回 task_id，轮询 /tasks/{task_id}） | before_report_id, after_report_id, use_llm | task_id, state, kind, poll_url |
| GET | `/api/v1/documents/{document_id}` | 读取解析结果（章节/段落/表格，供报告页原文预览） | path/query: document_id | document_id, source_name, sections, paragraphs, tables, warnings, parser |
| GET | `/api/v1/health` | 健康检查（存活与配置状态） | — | status, app_env, docs_enabled |
| GET | `/api/v1/reports` | 列出当前会话的报告（供修改对比选择） | — | [report_id, document_id, document_name, counts, created_at] |
| GET | `/api/v1/reports/{report_id}` | 读取单份报告全文（findings 含锚点） | path/query: report_id | report_id, document_name, checklist_version, findings, counts, duration_ms, tokens, notes… |
| POST | `/api/v1/reports/{report_id}/chat` | 提交报告问答任务（scope=finding 追问单条 / scope=fulltext 全文自由提问；202 返回 task_id，轮询 /tasks/{task_id}） | question, finding_id, history; path/query: report_id | task_id, state, kind, poll_url |
| GET | `/api/v1/reports/{report_id}/export` | 导出报告（format=markdown） | path/query: report_id, format | Markdown 文本（PlainTextResponse） |
| POST | `/api/v1/reports/{report_id}/revision` | 提交生成修改稿任务（按报告问题生成修改稿并二次审查；202 返回 task_id，轮询 /tasks/{task_id}） | path/query: report_id | task_id, state, kind, poll_url |
| POST | `/api/v1/reviews` | 提交结构化审查任务（202 返回 task_id，轮询 /api/v1/tasks/{task_id}） | document_id, use_llm, demote_on_figures | task_id, state, kind, poll_url |
| POST | `/api/v1/sessions/purge` | 删除当前会话数据（数据库 + 临时文件） | — | status |
| GET | `/api/v1/tasks/{task_id}` | 查询任务状态与结果（queued/running/succeeded/failed；succeeded 时 result 即旧同步响应体） | path/query: task_id | task_id, kind, state, result, error, created_at, updated_at |
| POST | `/api/v1/uploads` | 上传 DOCX 并解析 | file (DOCX) | document_id, parser, sections, paragraph_count, citation_count, reference_count, warnings |

## 2. 说明
- 第 1 节的“关键响应字段”直接来自 OpenAPI（各接口已声明 `response_model`）。
- `RESPONSE_FIELDS` 仅作为无 JSON 结构接口（如 Markdown 导出）的补充说明。

## 3. 约定
- 统一前缀 `/api/v1`；会话通过 HttpOnly Cookie（`pm_session`）维护，免登录。
- 错误响应统一为 `{code, message, request_id}`；跨会话访问他人资源返回 404。
- 审查参数：`use_llm`（是否启用模型顾问，**不传则用服务端默认 `LLM_DEFAULT_ENABLED=true`，即默认启用**）、`demote_on_figures`（图表未解析时是否保守降级，不传则用服务端默认）。
- 追问上下文：`history` 为客户端可选的 `[{role, content}]`（服务端仅在落库历史为空时采用）；上限 `CHAT_HISTORY_MAX_TURNS=10`（即 20 条消息）与 `CHAT_HISTORY_MAX_CHARS=8000`（含 system），超出时**整轮截断**并置 `truncated=true`。
- 报告问答作用域：`scope=finding`（追问，注入单条问题上下文）与 `scope=fulltext`（自由提问，注入全文 DATA 区，`QA_FULLTEXT_MAX_CHARS=12000`）；两者共用同一轮数与字符上限。
- 对比参数：`use_llm`（是否用模型结合全文生成修改稿补写，不传则用服务端默认；关闭则退回清单规范句式）；未提供 `after_report_id` 时后端自动生成修改稿并二次审查。
- 任务模式：四个重接口（`/reviews`、`/compare`、`/reports/{id}/chat`、`/reports/{id}/revision`）均**立即返回 202** 与 `{task_id, state, kind, poll_url}`，业务主体在受控线程池执行；前端轮询 `GET /api/v1/tasks/{task_id}`，`state=succeeded` 时 `result` 即旧同步响应体、`state=failed` 时 `error` 带 `code/message`。`TASK_MAX_WORKERS=2` 控制并发上限，`TASK_RETENTION_MINUTES=30` 控制终态/僵尸任务保留期。

## 4. 已知缺口
- 已解决：全部接口声明 `response_model`，OpenAPI 含响应结构；`tests/test_api_contract.py` 做前后端字段契约校验（含任务 result 字段）。
