"""在 README 与需求文档中建立 API 文档索引，并记录 response_model 缺口。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

readme = ROOT / "README.md"
text = readme.read_text(encoding="utf-8")
line = "- API 接口说明（与后端同步）→ docs/API接口说明.md；交互式文档 http://127.0.0.1:8000/docs"
if "API接口说明.md" not in text:
    anchor = "- 审查清单 v1（17 条）→ checklists/quant-ai-v1.json"
    if anchor in text:
        text = text.replace(anchor, anchor + "\n" + line)
    else:
        text = text.rstrip() + "\n" + line + "\n"
    readme.write_text(text, encoding="utf-8")
    print("README 已加入 API 文档索引")

req = ROOT / "docs" / "软件需求说明.md"
req_text = req.read_text(encoding="utf-8")
if "API接口说明.md" not in req_text:
    anchor = "- API 前缀 `/api/v1`；统一响应错误结构 `{code, message, request_id}`。"
    if anchor in req_text:
        req_text = req_text.replace(anchor, anchor + "\n- 接口清单与响应字段：`docs/API接口说明.md`（由 `backend/scripts/gen_api_doc.py` 从 OpenAPI 生成，改接口后需重新生成）。")
        req.write_text(req_text, encoding="utf-8")
        print("需求文档已加入 API 文档索引")
    else:
        print("[warn] 需求文档未找到 API 约定锚点")

gap = ROOT / "docs" / "开发规范与开发顺序.md"
gap_text = gap.read_text(encoding="utf-8")
if "response_model" not in gap_text:
    gap_text = gap_text.rstrip() + "\n\n### 工程缺口（新增）\n- P1：为主要接口补 `response_model`，使 OpenAPI 完整记录响应结构（当前响应字段见 `docs/API接口说明.md` 人工记录）。\n"
    gap.write_text(gap_text, encoding="utf-8")
    print("开发规范已记录 response_model 缺口")
