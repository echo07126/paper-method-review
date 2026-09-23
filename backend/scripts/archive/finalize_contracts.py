"""收尾：接口文档生成器输出响应字段；文档标记 response_model 缺口已解决。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 1) 生成器：表 1 增加“关键响应字段”（来自 OpenAPI，缺失时回退人工映射）
gen = ROOT / "backend" / "scripts" / "gen_api_doc.py"
text = gen.read_text(encoding="utf-8")
text = text.replace('        "| 方法 | 路径 | 用途 | 关键请求字段 |",\n        "| --- | --- | --- | --- |",',
                    '        "| 方法 | 路径 | 用途 | 关键请求字段 | 关键响应字段 |",\n        "| --- | --- | --- | --- | --- |",')
text = text.replace('            lines.append(f"| {method.upper()} | `{path}` | {PURPOSE.get(path, \'\')} | {request_fields} |")',
                    '            response_schema = operation.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema")\n'
                    '            response_fields = fields(spec, response_schema) if response_schema else RESPONSE_FIELDS.get(path, "text")\n'
                    '            lines.append(f"| {method.upper()} | `{path}` | {PURPOSE.get(path, \'\')} | {request_fields} | {response_fields} |")')
text = text.replace('    lines += ["", "## 2. 响应字段约定（与实现核对）", "", "| 路径 | 关键响应字段 |", "| --- | --- |"]\n    for path in sorted(RESPONSE_FIELDS):\n        lines.append(f"| `{path}` | {RESPONSE_FIELDS[path]} |")',
                    '    lines += ["", "## 2. 说明", "- 第 1 节的“关键响应字段”直接来自 OpenAPI（各接口已声明 `response_model`）。",\n              "- `RESPONSE_FIELDS` 仅作为无 JSON 结构接口（如 Markdown 导出）的补充说明。"]')
text = text.replace('        "- 当前路由以 `dict` 返回、未声明 `response_model`，因此第 1 节的 OpenAPI 无响应结构；第 2 节为人工核对记录。",\n        "- 待办（P1）：为主要接口补 `response_model`，让 OpenAPI 自动覆盖响应结构。",',
                    '        "- 已解决：全部接口声明 `response_model`，OpenAPI 含响应结构；`tests/test_api_contract.py` 做前后端字段契约校验。",')
gen.write_text(text, encoding="utf-8")
print("gen_api_doc 已更新")

# 2) 需求文档 G-01 标记完成
req = ROOT / "docs" / "软件需求说明.md"
req_text = req.read_text(encoding="utf-8")
old_g01 = "| G-01 | 工程 | API 契约与错误码 | 已提供接口清单与响应字段 → `docs/API接口说明.md`（由 `backend/scripts/gen_api_doc.py` 从 OpenAPI 生成）；统一错误结构 `{code, message, request_id}` 已实现 | 剩余：为主要接口补 `response_model`，使 OpenAPI 自动覆盖响应结构；改接口后重新生成文档 | P0 | W1（部分完成） |"
new_g01 = "| G-01 | 工程 | API 契约与错误码 | 已完成：全部接口声明 `response_model`（OpenAPI 含响应结构）+ 统一错误结构 `{code, message, request_id}` + 契约测试 `tests/test_api_contract.py` | 文档索引 `docs/API接口说明.md`（改接口后重新生成） | P0 | W1（已完成） |"
if old_g01 in req_text:
    req.write_text(req_text.replace(old_g01, new_g01), encoding="utf-8")
    print("需求文档 G-01 标记完成")
else:
    print("[warn] 未找到 G-01 行")

# 3) 开发规范：把“工程缺口”改为已解决
dev = ROOT / "docs" / "开发规范与开发顺序.md"
dev_text = dev.read_text(encoding="utf-8")
old_gap = "### 工程缺口（新增）\n- P1：为主要接口补 `response_model`，使 OpenAPI 完整记录响应结构（当前响应字段见 `docs/API接口说明.md` 人工记录）。"
new_gap = "### 工程缺口（已解决）\n- ~~P1：为主要接口补 `response_model`~~ → **已完成**：全部接口已声明 `response_model`，OpenAPI 自动含响应结构；新增契约测试 `tests/test_api_contract.py`（校验接口声明完整 + 前端字段与后端一致）。"
if old_gap in dev_text:
    dev.write_text(dev_text.replace(old_gap, new_gap), encoding="utf-8")
    print("开发规范缺口已标记解决")
else:
    print("[warn] 未找到开发规范缺口段")
