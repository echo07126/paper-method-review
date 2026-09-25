"""图表感知：识别图/表引用，并在需要时对“证据可能位于图表中”的结论做保守降级。"""
import re

from app.models.schemas import DocumentIR, Element, Finding, Severity, Verdict

FIGURE_REF_PATTERN = re.compile(
    r"(图\s*\d+|图\s*[一二三四五六七八九十]+|附图\s*\d+|Figure\s*\d+|Fig\.?\s*\d+|表\s*\d+|Table\s*\d+|Supplementary\s+(?:Fig|Table))",
    re.IGNORECASE,
)

# 这些条目的正/负证据经常只出现在图表中（如 CI、样本量、重复次数、预处理细节）
DEMOTE_ITEMS = {"R-02", "R-09", "R-10", "R-12", "R-13"}

# 各条目的支撑性要素类型：这些要素若已在表体中被抽取到，说明表格内容已被引擎消费
ITEM_EVIDENCE_TYPES: dict[str, tuple[str, ...]] = {
    "R-02": ("sample_size", "sample_size_rationale"),
    "R-09": ("confidence_interval", "effect_size"),
    "R-10": ("repeats", "confidence_interval"),
    "R-12": ("hyperparameter",),
    "R-13": ("preprocessing",),
}


def find_figure_references(document: DocumentIR) -> list[dict]:
    references: list[dict] = []
    for paragraph in document.paragraphs:
        for match in FIGURE_REF_PATTERN.finditer(paragraph.text):
            references.append({"paragraph_index": paragraph.index, "text": match.group(0)})
    return references


def _table_anchor_indexes(document: DocumentIR | None) -> set[int]:
    return {table.anchor.paragraph_index for table in document.tables} if document else set()


def _evidence_in_tables(item_id: str, elements: list[Element] | None, table_indexes: set[int]) -> bool:
    """该条目的支撑性要素是否已在表体中被抽取到（表格内容已被消费，结论可判定）。"""
    if not elements or not table_indexes:
        return False
    types = set(ITEM_EVIDENCE_TYPES.get(item_id, ()))
    return any(
        element.type in types
        and any(anchor.paragraph_index in table_indexes for anchor in element.anchors)
        for element in elements
    )


def demote_for_figures(
    findings: list[Finding],
    document: DocumentIR | None = None,
    elements: list[Element] | None = None,
) -> list[Finding]:
    """图表未解析时，把可能依赖图表证据的规则结论降级为「存疑」，避免误报。

    表格结构化成功后（P2-2 / 需求 15.5.2），若某条目的支撑性要素已在表体中被抽取到，
    说明该结论已基于完整可判定信息，不再降级；表格为空或解析失败时保留原降级行为。
    """
    table_indexes = _table_anchor_indexes(document)
    demoted: list[Finding] = []
    for finding in findings:
        if (
            finding.provenance.get("engine") == "rule"
            and finding.verdict == Verdict.PROBLEM
            and finding.checklist_item_id in DEMOTE_ITEMS
            and not _evidence_in_tables(finding.checklist_item_id, elements, table_indexes)
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
