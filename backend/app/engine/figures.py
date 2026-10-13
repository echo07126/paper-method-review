"""图表感知：识别图/表引用，并在需要时对“证据可能位于图表中”的结论做保守降级。"""
import re

from app.models.schemas import DocumentIR, Element, Finding, Severity, Verdict

# 「图」「表」在中文里常出现在普通词语中（代表、试图、地图、发表、报表…），单字匹配会产生
# 幻影图表引用。这些前置字构成的是词语而非图表，故用定长反向断言排除；
# 注意不要误伤真正的图表词（插图 / 草图 / 挂图 / 截图 均以「图」结尾且成立，故未列入）。
NOT_A_FIGURE_PREFIX = "代试地意版蓝力贪宏企略"
NOT_A_TABLE_PREFIX = "代发报外手仪师华填图"
# 编号后紧跟量词/单位时是「数量」而非图表编号（「代表3个模型」中的「表3」不是表引用）
NUMBER_IS_A_QUANTITY = r"(?!\s*(?:个|种|类|名|例|次|篇|条|张|幅|台|只|人|年|月|日|周|%|％|个百分点))"
FIGURE_REF_PATTERN = re.compile(
    rf"(?<![{NOT_A_FIGURE_PREFIX}])图\s*\d+"
    rf"|(?<![{NOT_A_FIGURE_PREFIX}])图\s*[一二三四五六七八九十]+"
    rf"|附图\s*\d+"
    rf"|Figure\s*\d+"
    rf"|Fig\.?\s*\d+"
    rf"|(?<![{NOT_A_TABLE_PREFIX}])表\s*\d+"
    rf"|Table\s*\d+"
    rf"|Supplementary\s+(?:Fig|Table)"
    + NUMBER_IS_A_QUANTITY,
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
    """该条目的支撑性要素是否已在表体中被抽取到（表格内容已被消费，结论可判定）。

    必须同时要求 `element.in_table`：表体要素的锚点就是表格上方正文段的段落序号，
    只看锚点会把「表格上方段落里的证据」误判成表内证据，从而漏掉应有的降级。
    """
    if not elements or not table_indexes:
        return False
    types = set(ITEM_EVIDENCE_TYPES.get(item_id, ()))
    return any(
        element.in_table
        and element.type in types
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
