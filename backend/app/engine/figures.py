"""图表感知：识别图/表引用，并在需要时对“证据可能位于图表中”的结论做保守降级。"""
import re

from app.models.schemas import DocumentIR, Finding, Severity, Verdict

FIGURE_REF_PATTERN = re.compile(
    r"(图\s*\d+|图\s*[一二三四五六七八九十]+|附图\s*\d+|Figure\s*\d+|Fig\.?\s*\d+|表\s*\d+|Table\s*\d+|Supplementary\s+(?:Fig|Table))",
    re.IGNORECASE,
)

# 这些条目的正/负证据经常只出现在图表中（如 CI、样本量、重复次数、预处理细节）
DEMOTE_ITEMS = {"R-02", "R-09", "R-10", "R-12", "R-13"}


def find_figure_references(document: DocumentIR) -> list[dict]:
    references: list[dict] = []
    for paragraph in document.paragraphs:
        for match in FIGURE_REF_PATTERN.finditer(paragraph.text):
            references.append({"paragraph_index": paragraph.index, "text": match.group(0)})
    return references


def demote_for_figures(findings: list[Finding]) -> list[Finding]:
    """图表未解析时，把可能依赖图表证据的规则结论降级为「存疑」，避免误报。"""
    demoted: list[Finding] = []
    for finding in findings:
        if (
            finding.provenance.get("engine") == "rule"
            and finding.verdict == Verdict.PROBLEM
            and finding.checklist_item_id in DEMOTE_ITEMS
        ):
            demoted.append(
                finding.model_copy(
                    update={
                        "verdict": Verdict.UNCERTAIN,
                        "description": "[图表未解析，需人工确认] " + finding.description,
                        "provenance": {**finding.provenance, "evidence_gate": "figures_unparsed"},
                    }
                )
            )
        else:
            demoted.append(finding)
    return demoted
