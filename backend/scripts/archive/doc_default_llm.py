"""文档同步：模型顾问默认启用。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# gen_api_doc 约定补充默认值说明
gen = ROOT / "backend" / "scripts" / "gen_api_doc.py"
text = gen.read_text(encoding="utf-8")
old = '        "- 审查可选参数：`use_llm`（是否启用模型顾问）、`demote_on_figures`（图表未解析时是否保守降级，不传则用服务端默认）。",'
new = '        "- 审查参数：`use_llm`（是否启用模型顾问，**不传则用服务端默认 `LLM_DEFAULT_ENABLED=true`，即默认启用**）、`demote_on_figures`（图表未解析时是否保守降级，不传则用服务端默认）。",'
if old in text:
    gen.write_text(text.replace(old, new), encoding="utf-8")
    print("gen_api_doc 已补充默认值说明")

# 说明文档
m = ROOT / "materials" / "01-软件说明文档.md"
text = m.read_text(encoding="utf-8")
if "默认启用" not in text:
    text = text.replace(
        "- **顾问模式**：模型结论一律以「建议/存疑」呈现，不计入问题总数——保证报告精确率，同时把语义线索交给人工复核。",
        "- **顾问模式**：模型结论一律以「建议/存疑」呈现，不计入问题总数——保证报告精确率，同时把语义线索交给人工复核。\n"
        "- **默认启用**：模型顾问默认开启（服务端 `LLM_DEFAULT_ENABLED=true`，前端复选框默认勾选）；用户可手动关闭（仅规则判定，0 token）。单篇模型消耗约 0.3–0.8 万 tokens、耗时 10–40 秒（视条目数与论文类型）。",
    )
    m.write_text(text, encoding="utf-8")
    print("说明文档已补充默认启用说明")

# 开发规范
d = ROOT / "docs" / "开发规范与开发顺序.md"
text = d.read_text(encoding="utf-8")
if "LLM_DEFAULT_ENABLED" not in text:
    text = text.rstrip() + """

### 模型顾问启用策略（2026-09-17 调整）
- **默认启用**：`LLM_DEFAULT_ENABLED=true`（服务端默认），前端复选框默认勾选；`use_llm` 请求参数可覆盖（显式 false 即关闭、0 token）。
- 顾问模式不变：模型结论进「存疑」，问题判定仍由规则给出（`LLM_ADVISORY_ONLY=true`）。
- 成本参考：单篇（综述类 4 条目）约 0.3 万输入 / 0.2 万输出 tokens、约 11 秒；实证类 17 条目约 0.5 万输入 / 0.7 万输出、约 40 秒。
"""
    d.write_text(text, encoding="utf-8")
    print("开发规范已记录默认启用策略")
