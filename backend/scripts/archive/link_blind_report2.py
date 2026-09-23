"""索引第二份盲测报告并更新文档口径。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

s = ROOT / "samples" / "README.md"
text = s.read_text(encoding="utf-8")
text = text.replace(
    "| 综述/理论（review） | 1 | blind-001《机器学习中的线性回归》：用户盲测论文，期望 0 问题（防误报回归）|",
    "| 综述/理论（review） | 2 | blind-001《机器学习中的线性回归》、blind-002《模型参数的确定方法》：用户盲测论文，期望 0 问题（防误报回归）|",
)
text = text.replace(
    "> 另含 1 篇综述类盲测论文（blind-001，期望 0 问题）。盲测报告：`docs/盲测报告-机器学习中的线性回归.md`",
    "> 另含 2 篇综述/方法类盲测论文（blind-001/002，期望 0 问题）。盲测报告：`docs/盲测报告-机器学习中的线性回归.md`、`docs/盲测报告-模型参数的确定方法.md`",
)
s.write_text(text, encoding="utf-8")

d = ROOT / "docs" / "开发规范与开发顺序.md"
text = d.read_text(encoding="utf-8")
if "2026-09-17" not in text:
    text = text.rstrip() + """

### 第二次真机盲测（2026-09-17）
- 对象：用户提供的第二篇论文《机器学习与深度学习中模型参数的确定方法》（方法/综述类，22 章节、2 表、1 图、20 角标、12 文献）。
- 修复 2 项：①图表题（表1/表2/图1 等）不再被当作章节标题（章节数 24→22）；②R-15 锚点避开表格行（改指最后一段正文），并把“开放问题/挑战/展望”等纳入局限词表。
- 结果：该论文 0 问题、4 通过（R-01/R-15/R-REF-01/R-REF-02）、跳过 13 条实证类检查；review 组累计 2 篇、误报 0。
- 报告：`docs/盲测报告-模型参数的确定方法.md`
"""
    d.write_text(text, encoding="utf-8")

r = ROOT / "README.md"
text = r.read_text(encoding="utf-8")
line = "- 盲测报告 2（方法/综述论文实测）→ docs/盲测报告-模型参数的确定方法.md"
if "盲测报告 2" not in text:
    text = text.rstrip() + "\n" + line + "\n"
    r.write_text(text, encoding="utf-8")
print("文档已更新")
