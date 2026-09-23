"""把盲测报告与论文类型识别能力写入文档索引。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# samples/README
s = ROOT / "samples" / "README.md"
text = s.read_text(encoding="utf-8")
if "blind-001" not in text:
    text = text.replace(
        "| 公开改写（real） | 7 | 已完成（Europe PMC，全部 CC-BY；已去重并收紧许可策略）|",
        "| 公开改写（real） | 7 | 已完成（Europe PMC，全部 CC-BY；已去重并收紧许可策略）|\n| 综述/理论（review） | 1 | blind-001《机器学习中的线性回归》：用户盲测论文，期望 0 问题（防误报回归）|",
    )
    text = text.replace(
        "## 最终指标（12 篇 / 59 条标准答案；real-001 的 R-03 经复核撤销）",
        "## 最终指标（13 篇 / 67 条标准答案）\n\n> 另含 1 篇综述类盲测论文（blind-001，期望 0 问题）。盲测报告：`docs/盲测报告-机器学习中的线性回归.md`",
    )
    s.write_text(text, encoding="utf-8")
    print("samples/README 已更新")

# 开发规范：进度记录
d = ROOT / "docs" / "开发规范与开发顺序.md"
text = d.read_text(encoding="utf-8")
if "盲测" not in text:
    text = text.rstrip() + """

### 真机盲测（2026-09-16）
- 对象：用户提供的综述论文《机器学习中的线性回归：原理、方法与研究进展》（13 篇评测集外的新样本）。
- 修复 5 项：①论文类型识别（review/empirical/unknown，综述仅执行通用检查）；②角标“引用样式”过滤（排除 R²、O((d+1)³) 等数学上标，38→32）；③R-01 支持“本文以…系统阐述”等目标表述；④R-12 支持“通过交叉验证确定”并把“正则化系数”纳入超参词表；⑤repeats 支持“交叉验证”。
- 结果：该论文 0 问题、4 通过、明确提示跳过 13 条实证类检查；回归后夹具 41/41、真实 26/26、精确率 100%、定位 94%；测试 31 项全绿。
- 报告：`docs/盲测报告-机器学习中的线性回归.md`
"""
    d.write_text(text, encoding="utf-8")
    print("开发规范已记录盲测")

# 说明文档：实现原理补充类型识别
m = ROOT / "materials" / "01-软件说明文档.md"
text = m.read_text(encoding="utf-8")
if "论文类型识别" not in text:
    text = text.replace(
        "### 4.5 规则引擎（确定性判定）",
        """### 4.4.1 论文类型识别（避免对非实证论文误报）
- 先判定论文类型：`review`（综述/理论）、`empirical`（实证）、`unknown`（默认按实证处理）。
- 综述/理论论文只执行通用条目（R-01 研究目标、R-15 局限、R-REF-01/02 引用规范），并跳过 13 条实证类检查（数据划分/基线/消融/统计检验/置信区间/随机种子/预处理等），报告与前端均显式提示“已跳过”。
- 依据：标题/摘要中的“综述、研究进展、系统阐述、survey”等强信号 + 实证信号（数据集、样本量、基线、测试集、AUC…）计数对比。

### 4.5 规则引擎（确定性判定）""",
    )
    m.write_text(text, encoding="utf-8")
    print("说明文档已补充类型识别")

# README 索引
r = ROOT / "README.md"
text = r.read_text(encoding="utf-8")
line = "- 盲测报告（综述论文实测）→ docs/盲测报告-机器学习中的线性回归.md"
if "盲测报告" not in text:
    text = text.rstrip() + "\n" + line + "\n"
    r.write_text(text, encoding="utf-8")
    print("README 已索引盲测报告")
