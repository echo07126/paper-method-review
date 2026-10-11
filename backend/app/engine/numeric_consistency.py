"""R-DATA-* 数值自洽检测器族：纯数值运算，结论可承诺确定性（certainty=deterministic）。

这些检查不依赖语义模型，只看原文/表体里已经写出的数字是否自洽，因此：
- 结论为「确定性核验」（`Certainty.DETERMINISTIC`）；
- 条目 ID 为 `R-DATA-*`，属**清单外附加检查**（与 R-FIG-01 同类），
  不计入 17 条清单名额，也不进入 AC-2/AC-3 的检出率与误报分母。

当前覆盖：
- R-DATA-01：数据划分比例之和应为 10 或 100（如 7:1:2 / 70:15:15）；
- R-DATA-02：同一句里划分相关百分比之和应约为 100%；
- R-DATA-03：区间估计的点估计应落在其所给出的 95% 置信区间内。
"""
from __future__ import annotations

import re

from app.core.ids import new_id
from app.models.schemas import Anchor, Certainty, DocumentIR, Finding, Severity, Verdict

RATIO_ITEM = "R-DATA-01"
PERCENT_ITEM = "R-DATA-02"
CI_ITEM = "R-DATA-03"

SPLIT_CONTEXT = re.compile(r"(划分|训练集|验证集|测试集|占比|比例|分配)")
# 比例链：8:1:1 / 7：1：2 / 5:2:2:1（≥3 段整体求和，避免把 4 段划分误读成前 3 段；数字边界避免匹配 32000 内的片段）
RATIO_CHAIN = re.compile(r"(?<![\d.])(\d{1,3}(?:\s*[:：]\s*\d{1,3}){2,})(?![\d.])")
# 百分比：60% / 12.5%（排除「95% CI」这类置信度前缀）
PERCENT = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*%(?!\s*(?:CI|置信))", re.IGNORECASE)
# 划分语境邻域：百分比需落在划分关键词附近才纳入合计，避免把同段落的其它百分比一并求和
_SPLIT_WINDOW = 12
# 指标语境：紧邻这些词之后的百分比属评价指标（如「准确率 95%」），不参与划分合计（防误报）
METRIC_CONTEXT = re.compile(r"(准确率|精确率|精度|准确度|召回率|召回|灵敏度|特异度|F1|AUC|IoU|Dice|一致率|命中率|错误率)")
# 点估计 + 95% 置信区间：0.85（95% CI 0.80–0.90）/ 0.85 [0.80, 0.90]
CI_PAIR = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*[（(]?\s*95\s*%\s*(?:CI|置信区间)\s*[:：]?\s*[\[（(]?\s*"
    r"(\d+(?:\.\d+)?)\s*[-–—~～至,，]\s*(\d+(?:\.\d+)?)\s*[\]）)]?",
    re.IGNORECASE,
)


def _unit_texts(document: DocumentIR) -> list[tuple[str, int]]:
    """判定单元 = 正文段落 + 表体行，均带段落锚点。"""
    units: list[tuple[str, int]] = [(p.text, p.index) for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        units.extend(
            (" | ".join(cell for cell in row if cell), table.anchor.paragraph_index)
            for row in table.rows
            if any(cell for cell in row)
        )
    return units


def _finding(item_id: str, rule_id: str, headline: str, description: str, suggestion: str, index: int) -> Finding:
    return Finding(
        finding_id=new_id("F"),
        checklist_item_id=item_id,
        verdict=Verdict.PROBLEM,
        severity=Severity.LOW,
        certainty=Certainty.DETERMINISTIC,
        headline=headline,
        description=description,
        anchors=[Anchor(paragraph_index=index)],
        suggestion=suggestion,
        provenance={"engine": "rule", "rule_id": rule_id, "numeric_check": rule_id},
    )


def _check_ratio(text: str) -> str | None:
    for match in RATIO_CHAIN.finditer(text):
        parts = [int(part) for part in re.split(r"\s*[:：]\s*", match.group(1))]
        total = sum(parts)
        if total not in (10, 100):
            rendered = ":".join(str(part) for part in parts)
            return f"划分比例 {rendered} 之和为 {total}，既非 10（按份数）也非 100（按百分比）"
    return None


def _is_split_share(text: str, start: int, end: int) -> bool:
    """判断某百分比是否属「划分份额」：靠近划分关键词，且不是紧跟在评价指标名词之后。"""
    if METRIC_CONTEXT.search(text[max(0, start - 8) : start]):
        return False
    return any(
        match.start() - end <= _SPLIT_WINDOW and start - match.end() <= _SPLIT_WINDOW
        for match in SPLIT_CONTEXT.finditer(text)
    )


def _check_percent(text: str) -> str | None:
    values = [
        float(match.group(1))
        for match in PERCENT.finditer(text)
        if _is_split_share(text, match.start(), match.end())
    ]
    if len(values) < 2:
        return None
    total = sum(values)
    if not (99.5 <= total <= 100.5):
        rendered = " + ".join(f"{v:g}%" for v in values)
        return f"划分相关百分比 {rendered} 之和为 {total:g}%，与 100% 不一致"
    return None


def _check_ci(text: str) -> str | None:
    for match in CI_PAIR.finditer(text):
        point = float(match.group(1))
        low, high = float(match.group(2)), float(match.group(3))
        if low > high:
            low, high = high, low
        if not (low <= point <= high):
            return f"点估计 {point:g} 不在 95% 置信区间 [{low:g}, {high:g}] 内"
    return None


def check_numeric_consistency(document: DocumentIR) -> list[Finding]:
    """对全文（含表体）做数值自洽核验，返回确定性结论列表（无问题则为空）。"""
    findings: list[Finding] = []
    for text, index in _unit_texts(document):
        if SPLIT_CONTEXT.search(text):
            ratio_issue = _check_ratio(text)
            if ratio_issue:
                findings.append(
                    _finding(
                        RATIO_ITEM,
                        RATIO_ITEM,
                        "数据划分比例之和自洽性存疑",
                        f"原文：「{text.strip()[:80]}」——{ratio_issue}。",
                        "核对训练/验证/测试集划分比例，使其之和为 10（份数）或 100（百分比）。",
                        index,
                    )
                )
            percent_issue = _check_percent(text)
            if percent_issue:
                findings.append(
                    _finding(
                        PERCENT_ITEM,
                        PERCENT_ITEM,
                        "数据划分百分比合计自洽性存疑",
                        f"原文：「{text.strip()[:80]}」——{percent_issue}。",
                        "核对各组划分百分比，使其合计为 100%。",
                        index,
                    )
                )
        ci_issue = _check_ci(text)
        if ci_issue:
            findings.append(
                _finding(
                    CI_ITEM,
                    CI_ITEM,
                    "置信区间与点估计不一致",
                    f"原文：「{text.strip()[:80]}」——{ci_issue}。",
                    "核对点估计与置信区间上下限，确保点估计落在区间内。",
                    index,
                )
            )
    return findings