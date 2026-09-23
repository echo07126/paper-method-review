"""一次性文档补丁：需求 v0.7（图表识读列入二期、规则 17 条、分组指标）+ 开发规范 + 说明文档。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
req = ROOT / "docs" / "软件需求说明.md"
dev = ROOT / "docs" / "开发规范与开发顺序.md"
doc = ROOT / "materials" / "01-软件说明文档.md"


def patch(path: Path, pairs: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if old in text:
            text = text.replace(old, new)
        else:
            print(f"  [skip] {path.name}: 未找到锚点 -> {old[:28]}...")
    path.write_text(text, encoding="utf-8")


changelog_anchor = "- 原因：一期聚焦「闭环 + 评测达标」，不为未验证格式投入解析成本；接口预留已保证二期可平滑接入。"
changelog_new = changelog_anchor + """

**v0.6 → v0.7 变更（本次）**
- 规则库由 12 条扩展到 **17 条**（新增 R-01 研究目标、R-06 评价指标、R-10 重复实验与方差、R-12 超参数依据、R-13 预处理与不平衡）。
- 评测口径分层：`samples/fixtures/`（规则夹具）与 `samples/real/`（真实论文改写）分开统计，不再混算。
- **图表处理策略**：一期不解析图片/图表内部数据；已落地「图片计数警告 + 报告提示 + 可切换保守模式（`demote_on_figures`，把可能依赖图表证据的条目降级为存疑）」；**图表识读（内嵌图片 + OCR/视觉模型）列入二期**（见 16.1、14.2）。"""

patch(req, [
    ("# 论文方法论审查助手 · 软件需求说明（v0.6）", "# 论文方法论审查助手 · 软件需求说明（v0.7）"),
    (changelog_anchor, changelog_new),
    ("| 公式 / 图片 | ✘（不进入审查依据） | ✘ | ✘ |",
     "| 公式 / 图片 / 图表内数据 | ✘（一期仅解析图注文本，图内数据不解析） | 二期：抽取内嵌图片 + OCR/视觉模型识读 | ✘ |"),
    ("- 二期（v1.1–v1.5）：PDF 解析实现（基础文字 → 版面/坐标高亮）、OCR 扫描件、账号体系与跨设备历史、清单扩展至 40+、多学科模板、Word / HTML 导出、批量审查。",
     "- 二期（v1.1–v1.5）：PDF 解析实现（基础文字 → 版面/坐标高亮）、OCR 扫描件、**图表识读（抽取内嵌图片 → OCR / 视觉多模态模型 → 图内文本与图表数值并入 DocumentIR，带图锚点供规则消费）**、账号体系与跨设备历史、清单扩展至 40+、多学科模板、Word / HTML 导出、批量审查。"),
])

dev_row_old = "| **+ 补齐 R-01/06/10/12/13 规则 + 夹具/真实分组 + 图表防护（当前）** | **夹具 41/41 = 100%；真实 26/26 = 100%** | **100%** | 真实样本 AC-3 **85%**、合计 **94%**；夹具更名 fixtures 并与真实指标分开统计；图表未解析时有提示与可选保守降级（DEMOTE_ON_FIGURES） |"
dev_row_new = """| 补齐 R-01/06/10/12/13 规则 + 夹具/真实分组 | 夹具 41/41 = 100%；真实 26/26 = 100% | 100% | 真实 AC-3 85%、合计 94% |
| **+ 图表保守模式可切换 + 图表识读列入二期（当前）** | 同上 | 100% | 规则共 17 条；测试 21 项；接口级验证：严格 7 问题 → 保守 4 问题 + 3 存疑 |"""
patch(dev, [(dev_row_old, dev_row_new)])

dev_text = dev.read_text(encoding="utf-8")
if "二期待办（Roadmap 摘要）" not in dev_text:
    dev_text = dev_text.rstrip() + """

### 二期待办（Roadmap 摘要）
- **图表识读（二期）**：抽取 DOCX 内嵌图片 → OCR / 视觉多模态模型 → 图内文本与图表数值并入 DocumentIR（带图锚点）→ 规则消费；需评估精度与成本。
- PDF 解析实现（基础文字 → 版面/坐标高亮）、OCR 扫描件、账号体系、清单扩至 40+、多学科模板、Word/HTML 导出、批量审查。
"""
    dev.write_text(dev_text, encoding="utf-8")

patch(doc, [
    ("  3. 提供可选保守模式 `DEMOTE_ON_FIGURES=true`：把可能依赖图表证据的条目（R-02/R-09/R-10/R-12/R-13）降级为「存疑」，避免误报。",
     "  3. 提供**可切换的保守模式**：默认由配置 `DEMOTE_ON_FIGURES` 决定，也可在**每次审查请求**中用 `demote_on_figures` 覆盖（前端「解析预览」页有勾选项）；开启后把可能依赖图表证据的条目（R-02/R-09/R-10/R-12/R-13）降级为「存疑」，避免误报。"),
    ("- **可扩展（二期）**：抽取内嵌图片 → OCR / 多模态模型读图",
     "- **可扩展（已列入二期路线，见需求 16.1）**：抽取内嵌图片 → OCR / 多模态模型读图"),
])

print("doc patch done")
