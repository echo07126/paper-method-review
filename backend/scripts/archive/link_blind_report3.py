"""索引第三份盲测报告并更新文档口径。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

s = ROOT / "samples" / "README.md"
text = s.read_text(encoding="utf-8")
if "blind-003" not in text:
    text = text.replace(
        "| 综述/理论（review） | 2 | blind-001《机器学习中的线性回归》、blind-002《模型参数的确定方法》：用户盲测论文，期望 0 问题（防误报回归）|",
        "| 综述/理论（review） | 2 | blind-001/blind-002：用户盲测论文，期望 0 问题（防误报回归）|\n"
        "| 规范实证（empirical） | 1 | blind-003《多尺度卷积与类别加权损失的中文短文本分类》：规范实证论文，期望 0 问题（防误报回归）|",
    )
    text = text.replace(
        "> 另含 2 篇综述/方法类盲测论文（blind-001/002，期望 0 问题）。盲测报告：`docs/盲测报告-机器学习中的线性回归.md`、`docs/盲测报告-模型参数的确定方法.md`",
        "> 另含 3 篇盲测论文（blind-001/002 综述类、blind-003 规范实证，期望 0 问题）。盲测报告：`docs/盲测报告-机器学习中的线性回归.md`、`docs/盲测报告-模型参数的确定方法.md`、`docs/盲测报告-中文短文本分类.md`",
    )
    s.write_text(text, encoding="utf-8")

d = ROOT / "docs" / "开发规范与开发顺序.md"
text = d.read_text(encoding="utf-8")
if "第三次真机盲测" not in text:
    text = text.rstrip() + """

### 第三次真机盲测（2026-09-17，规范实证论文）
- 对象：《多尺度卷积与类别加权损失的中文短文本分类》（18 章节、4 表、2 图、33 角标、18 文献）。
- 修复 1 项：**R-03 误把「验证集调参」当泄漏**（验证集用于超参数选择属规范做法）→ 收紧为「调参 + 测试集」共现且未声明“测试集仅用于最终评估”才判泄漏；夹具 synthetic-001 改为真正的泄漏场景；新增 2 条测试。
- 结果：修复前 1 误报 → 修复后 **0 问题、16 通过**（与人工标准答案一致）；empirical 组误报 0；测试 33 项全绿。
- 报告：`docs/盲测报告-中文短文本分类.md`
"""
    d.write_text(text, encoding="utf-8")

r = ROOT / "README.md"
text = r.read_text(encoding="utf-8")
line = "- 盲测报告 3（规范实证论文实测）→ docs/盲测报告-中文短文本分类.md"
if "盲测报告 3" not in text:
    text = text.rstrip() + "\n" + line + "\n"
    r.write_text(text, encoding="utf-8")
print("文档已更新")
