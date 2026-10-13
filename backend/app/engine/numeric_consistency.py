"""R-DATA-* 数值自洽检测器族：纯数值运算，结论可承诺确定性（certainty=deterministic）。

这些检查不依赖语义模型，只看原文/表体里已经写出的数字是否自洽，因此：
- 结论为「确定性核验」（`Certainty.DETERMINISTIC`）；
- 条目 ID 为 `R-DATA-*`，属**清单外附加检查**（与 R-FIG-01 同类），
  不计入 17 条清单名额，也不进入 AC-2/AC-3 的检出率与误报分母。

当前覆盖：
- R-DATA-01：数据划分比例之和应为 10（按份数）或 100（按百分比）；
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
# 比例链：8:1:1 / 7：1：2 / 5:2:2:1 / 8:2（≥2 段整体求和，避免把 4 段划分误读成前 3 段；
# 数字边界避免匹配 32000 内的片段）
RATIO_CHAIN = re.compile(r"(?<![\d.])(\d{1,3}(?:\s*[:：]\s*\d{1,3})+)(?![\d.])")
# 比例口径：既可以按份数写（各份之和 10，如 8:1:1），也可以按百分比写（之和 100）。
# 之和 < 10 时与合法的份数写法不可区分（4:1:1、8:2 都是有效写法，缺少分母无法判定），不报；
# 之和 > 10 且 ≠ 100 时既非份数也非百分比，才判为不一致——后者正是 7:1:5 这类笔误。
RATIO_PARTS_TOTAL = 10
RATIO_PERCENT_TOTAL = 100
# 百分比：60% / 12.5%（排除「95% CI」这类置信度前缀）
PERCENT = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*%(?!\s*(?:CI|置信))", re.IGNORECASE)
# 划分语境邻域：百分比需落在划分关键词附近才纳入合计，避免把同段落的其它百分比一并求和
_SPLIT_WINDOW = 12
# 指标语境：紧邻这些词之后的百分比属评价指标（如「准确率 95%」），不参与划分合计（防误报）
METRIC_CONTEXT = re.compile(r"(准确率|精确率|精度|准确度|召回率|召回|灵敏度|特异度|F1|AUC|IoU|Dice|一致率|命中率|错误率)")
# 点估计 + 95% 置信区间：0.85（95% CI 0.80–0.90）/ 85%（95% CI 80%–90%）
# 点估计与上下限各自可带 %（中文论文常写成百分比）；三者单位必须一致才做比较，
# 混用（如「92%（95% CI 0.88–0.96）」）口径不明，保守跳过而不是误报。
CI_PAIR = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*(%)?\s*[（(]?\s*95\s*%\s*(?:CI|置信区间)\s*[:：]?\s*[\[（(]?\s*"
    r"(\d+(?:\.\d+)?)\s*(%)?\s*[-–—~～至,，]\s*(\d+(?:\.\d+)?)\s*(%)?\s*[\]）)]?",
    re.IGNORECASE,
)
# 相邻划分百分比之间允许出现的连接成分：纯分隔符，或一个划分组名。
# 不允许「占/为」等谓语，避免把「训练集占 80%…其中正类占比 5%」这类组内比例并进同一组合计。
_PERCENT_GAP = re.compile(
    r"^[\s、,，和与及/：:；;]*(?:训练集|验证集|测试集|数据集|数据|划分|部分)?[\s、,，和与及/：:；;]*$"
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
        if total in (RATIO_PARTS_TOTAL, RATIO_PERCENT_TOTAL) or total < RATIO_PARTS_TOTAL:
            continue
        rendered = ":".join(str(part) for part in parts)
        return (
            f"划分比例 {rendered} 之和为 {total}，既不是按份数的 {RATIO_PARTS_TOTAL}，"
            f"也不是按百分比的 {RATIO_PERCENT_TOTAL}"
        )
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
    """只对「同一组连续枚举」的划分百分比求和。

    仅按邻近窗口求和会把不同量纲的百分比并到一起（如「训练集占 80%，验证集占 20%，
    其中训练集正类占比 5%」→ 105%），因此先按连接成分把百分比切成组，组内才求和。
    """
    hits = [
        (match.start(), match.end(), float(match.group(1)))
        for match in PERCENT.finditer(text)
        if _is_split_share(text, match.start(), match.end())
    ]
    groups: list[list[float]] = []
    previous_end: int | None = None
    for start, end, value in hits:
        if previous_end is None or not _PERCENT_GAP.match(text[previous_end:start]):
            groups.append([])
        groups[-1].append(value)
        previous_end = end

    for values in groups:
        if len(values) < 2:
            continue
        total = sum(values)
        if not (99.5 <= total <= 100.5):
            rendered = " + ".join(f"{v:g}%" for v in values)
            return f"划分相关百分比 {rendered} 之和为 {total:g}%，与 100% 不一致"
    return None


def _check_ci(text: str) -> str | None:
    for match in CI_PAIR.finditer(text):
        point = float(match.group(1))
        low, high = float(match.group(3)), float(match.group(5))
        # 单位混用（点估计用小数、区间用百分比，或反之）时口径不明，保守跳过
        if len({bool(match.group(2)), bool(match.group(4)), bool(match.group(6))}) > 1:
            continue
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