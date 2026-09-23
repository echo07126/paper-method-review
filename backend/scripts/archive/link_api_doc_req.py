"""在需求文档 Gap Register 的 G-01 行补上 API 文档索引与剩余缺口。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
req = ROOT / "docs" / "软件需求说明.md"
text = req.read_text(encoding="utf-8")
old = "| G-01 | 工程 | API 契约与错误码 | 未定义 | OpenAPI 文档 + 统一错误结构 `{code, message, request_id}` + 常见错误码表 | P0 | W1 |"
new = "| G-01 | 工程 | API 契约与错误码 | 已提供接口清单与响应字段 → `docs/API接口说明.md`（由 `backend/scripts/gen_api_doc.py` 从 OpenAPI 生成）；统一错误结构 `{code, message, request_id}` 已实现 | 剩余：为主要接口补 `response_model`，使 OpenAPI 自动覆盖响应结构；改接口后重新生成文档 | P0 | W1（部分完成） |"
if old in text:
    text = text.replace(old, new)
    req.write_text(text, encoding="utf-8")
    print("G-01 已更新")
else:
    print("[warn] 未找到 G-01 行")
