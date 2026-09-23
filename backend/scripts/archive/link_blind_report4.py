"""索引第四份盲测报告（预埋缺陷论文）并更新文档口径。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

s = ROOT / "samples" / "README.md"
text = s.read_text(encoding="utf-8")
if "blind-004" not in text:
    text = text.replace(
        "| 规范实证（empirical） | 1 | blind-003《多尺度卷积与类别加权损失的中文短文本分类》：规范实证论文，期望 0 问题（防误报回归）|",
        "| 规范实证（empirical） | 1 | blind-003：规范实证论文，期望 0 问题（防误报回归）|\n"
        "| 预埋缺陷（planted） | 1 | blind-004《基于多尺度卷积与改进注意力机制的中文短文本分类方法》：预埋 16 条缺陷（本方覆盖 14 条），用于阳性召回 |",
    )
    text = text.replace(
        "> 另含 3 篇盲测论文（blind-001/002 综述类、blind-003 规范实证，期望 0 问题）。",
        "> 另含 4 篇盲测论文（blind-001/002 综述类、blind-003 规范实证、blind-004 预埋缺陷）。",
    )
    text = text.replace(
        "`docs/盲测报告-机器学习中的线性回归.md`、`docs/盲测报告-模型参数的确定方法.md`、`docs/盲测报告-中文短文本分类.md`",
        "`docs/盲测报告-机器学习中的线性回归.md`、`docs/盲测报告-模型参数的确定方法.md`、`docs/盲测报告-中文短文本分类.md`、`docs/盲测报告-预埋缺陷实证论文.md`",
    )
    s.write_text(text, encoding="utf-8")

d = ROOT / "docs" / "开发规范与开发顺序.md"
text = d.read_text(encoding="utf-8")
if "第四次真机盲测" not in text:
    text = text.rstrip() + """

### 第四次真机盲测（2026-09-17，预埋缺陷实证论文）
- 对象：《基于多尺度卷积与改进注意力机制的中文短文本分类方法》（生成方自检 16/16 缺陷落位；本清单可判定 14 条）。
- 规则增强 5 项：R-07 需具名检验；R-04 单一基线识别；R-06 分类指标校验；R-12 需搜索范围；R-03 需划分比例/种子并识别“测试集调参”泄漏。R-08 增加 AI 适用性守卫。
- 锚点改为**按章节定位**（数据划分/基线方法/模型结构/评价指标/主结果/统计检验/训练细节/讨论），排除标题、摘要与表格行；对 4 篇真实样本按“锚点=该信息应出现的段落”复核 GT。
- 结果：预埋缺陷 **14/14 = 100% 检出、定位 93%**；真实样本定位 100%；合计 **82/82 = 100% 检出、精确率 100%、定位 96%**；测试 38 项全绿。
- 报告：`docs/盲测报告-预埋缺陷实证论文.md`
"""
    d.write_text(text, encoding="utf-8")

r = ROOT / "README.md"
text = r.read_text(encoding="utf-8")
line = "- 盲测报告 4（预埋缺陷实证论文实测：14/14 检出）→ docs/盲测报告-预埋缺陷实证论文.md"
if "盲测报告 4" not in text:
    text = text.rstrip() + "\n" + line + "\n"
    r.write_text(text, encoding="utf-8")
print("文档已更新")
