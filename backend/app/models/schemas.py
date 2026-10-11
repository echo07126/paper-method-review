from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Severity(str, Enum):
    HIGH = "high"
    MID = "mid"
    LOW = "low"


class Certainty(str, Enum):
    """确定性等级：与 severity 正交——severity 衡量问题多严重，certainty 衡量我们多确定。

    - deterministic：判据依赖 OOXML 结构或数值运算（角标编号集合、文献编号集合等），可承诺正确；
    - suspected：正则 + 多条件命中的高置信疑似，仅作提示，需人工确认；
    - undetermined：证据不足，本项未能判定（替代此前静默 return []）。
    """

    DETERMINISTIC = "deterministic"
    SUSPECTED = "suspected"
    UNDETERMINED = "undetermined"


class Verdict(str, Enum):
    PASS = "pass"
    PROBLEM = "problem"
    NOT_APPLICABLE = "not_applicable"
    UNCERTAIN = "uncertain"


class Anchor(BaseModel):
    paragraph_index: int
    sentence_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    page: int | None = None
    bbox: list[float] | None = None


class Sentence(BaseModel):
    index: int
    text: str
    char_start: int
    char_end: int


class Paragraph(BaseModel):
    index: int
    text: str
    style: str = "Normal"
    is_heading: bool = False
    sentences: list[Sentence] = Field(default_factory=list)


class Section(BaseModel):
    id: str
    title: str
    level: int = 1
    paragraph_index: int
    confidence: float = 1.0
    needs_review: bool = False


class CitationMarker(BaseModel):
    text: str
    numbers: list[int] = Field(default_factory=list)
    anchor: Anchor
    unresolved: list[int] = Field(default_factory=list)


class ReferenceEntry(BaseModel):
    number: int
    text: str
    anchor: Anchor


class Table(BaseModel):
    id: str
    index: int
    caption: str = ""
    rows: list[list[str | None]] = Field(default_factory=list)
    header_rows: int = 0
    n_rows: int = 0
    n_cols: int = 0
    anchor: Anchor


class ImageRef(BaseModel):
    """内嵌图片：落盘到会话临时目录，供 L3 视觉识读（P2-3 / 需求 15.5.1）。"""

    id: str
    index: int
    media_type: str = ""
    byte_size: int = 0
    filename: str = ""
    caption: str = ""
    caption_index: int | None = None
    anchor: Anchor


class DocumentIR(BaseModel):
    source_name: str
    parser: str
    parser_version: str
    language: str = "zh"
    sections: list[Section] = Field(default_factory=list)
    paragraphs: list[Paragraph] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    images: list[ImageRef] = Field(default_factory=list)
    citations: list[CitationMarker] = Field(default_factory=list)
    references: list[ReferenceEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class ReviewItem(BaseModel):
    id: str
    version: str = "1.0"
    category: str
    templates: list[str] = Field(default_factory=list)
    applies_when: str | None = None
    requires: list[str] = Field(default_factory=list)
    severity_default: Severity = Severity.MID
    # 判定主体分工（条目级「审查拆分」的唯一事实源）：
    #   rule     —— 判据依赖 OOXML 结构或数值运算（引用编号对账等），规则侧判定，不送模型；
    #   llm      —— 语义类判据，模型主导，结论必须挂到要素/原文锚点（无证据仍降级为存疑）；
    #   advisory —— 证据常落在图/表或判定本身偏软，模型只出「建议」，一律降级为存疑。
    judge: Literal["rule", "llm", "advisory"] = "llm"
    title: str
    description: str = ""
    suggestion_template: str = ""
    # 「修改后」示范句式：供报告页「修改后展示」直接渲染（可选、与判定解耦）
    revision_template: str = ""
    evidence_policy: str = "requires_element"
    source_refs: list[str] = Field(default_factory=list)


class Element(BaseModel):
    id: str
    type: str
    value: Any = None
    anchors: list[Anchor] = Field(default_factory=list)
    confidence: float = 1.0


class Finding(BaseModel):
    finding_id: str
    checklist_item_id: str
    verdict: Verdict
    severity: Severity
    certainty: Certainty = Certainty.SUSPECTED
    headline: str
    description: str = ""
    evidence_elements: list[str] = Field(default_factory=list)
    anchors: list[Anchor] = Field(default_factory=list)
    suggestion: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)
    # 输出质量量化（与 severity / certainty 均正交）：confidence 为 0–1 连续置信度，
    # 由「判据基分 × 证据 × 一致性 × 门控因子」合成；grade 为据此划分的 A/B/C/D 档
    # （A 高置信可直接采信、B 中置信建议确认、C 低置信需复核、D 未能判定/证据不足）。
    confidence: float = 0.0
    grade: Literal["A", "B", "C", "D"] = "B"


class ReviewReport(BaseModel):
    report_id: str
    document_name: str
    checklist_version: str
    findings: list[Finding] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    duration_ms: int = 0
    tokens: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    figure_references: int = 0
    demote_on_figures: bool = False
    paper_type: str = "unknown"
    # 质量卡：分级分布、门控分布、平均置信度与审查率（assessed/applicable），供前端与导出消费。
    quality: dict[str, Any] = Field(default_factory=dict)


class JobState(str, Enum):
    """任务状态（jobs.state 列的取值），与 app/tasks/executor.py 中的常量一致。"""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TaskAccepted(BaseModel):
    """重接口入队响应（HTTP 202）：提交后由前端轮询 /tasks/{task_id} 取结果。"""

    task_id: str
    state: str
    kind: str
    # 相对 API 前缀（/api/v1）的轮询路径，如 /tasks/job_xxx
    poll_url: str


class TaskStatusResponse(BaseModel):
    task_id: str
    kind: str
    state: str
    # 成功时为旧同步响应体（字段与改造前逐字段一致）；失败时 error 带 code/message
    result: dict | None = None
    error: dict | None = None
    created_at: str
    updated_at: str


class SectionSummary(BaseModel):
    title: str
    paragraph_index: int
    needs_review: bool = False


class UploadResponse(BaseModel):
    document_id: str
    parser: str
    sections: list[SectionSummary] = Field(default_factory=list)
    paragraph_count: int
    citation_count: int
    reference_count: int
    warnings: list[str] = Field(default_factory=list)


class DocumentResponse(BaseModel):
    document_id: str
    source_name: str | None = None
    sections: list[Section] = Field(default_factory=list)
    paragraphs: list[Paragraph] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parser: str | None = None


class ReviewCreateResponse(BaseModel):
    report_id: str
    counts: dict[str, int] = Field(default_factory=dict)
    duration_ms: int = 0
    tokens: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    figure_references: int = 0
    demote_on_figures: bool = False
    paper_type: str = "unknown"
    quality: dict[str, Any] = Field(default_factory=dict)


class ReportSummary(BaseModel):
    report_id: str
    document_id: str
    document_name: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    created_at: str


class CompareFinding(BaseModel):
    """对比页逐条明细：与 Finding 同构，供双栏问题清单直接渲染。

    revision_status 区分「可文字改写」与「结构性不可自动改写」：
    - rewritten：示范改写成功写入修改稿对应段落；
    - manual：结论依赖图表/数据/外部材料，必须作者本人核对后才算解决；
    - pending：附有示范改写，但未定位到可替换的段落。
    """

    checklist_item_id: str
    headline: str = ""
    severity: Severity = Severity.MID
    certainty: Certainty = Certainty.SUSPECTED
    verdict: Verdict = Verdict.PROBLEM
    anchors: list[Anchor] = Field(default_factory=list)
    description: str = ""
    suggestion: str = ""
    revision_status: Literal["rewritten", "manual", "pending"] = "pending"
    revision_note: str = ""


class CompareResponse(BaseModel):
    before: dict[str, int]
    after: dict[str, int]
    resolved: list[str]
    new: list[str]
    kept: list[str]
    # 明细在保持排序键不变的前提下追加，旧客户端字段不受影响
    before_findings: list[CompareFinding] = Field(default_factory=list)
    after_findings: list[CompareFinding] = Field(default_factory=list)
    resolved_findings: list[CompareFinding] = Field(default_factory=list)
    new_findings: list[CompareFinding] = Field(default_factory=list)
    kept_findings: list[CompareFinding] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatResponse(BaseModel):
    answer: str
    source: Literal["llm", "fallback"]
    tokens: dict[str, int] | None = None
    note: str | None = None
    session_id: str = ""
    history: list[ChatMessage] = Field(default_factory=list)
    truncated: bool = False
    # 提问作用域：finding = 针对某条审查问题；fulltext = 基于全文的自由提问
    scope: Literal["finding", "fulltext"] = "finding"


class PurgeResponse(BaseModel):
    status: str


class HealthResponse(BaseModel):
    status: str
    app_env: str
    docs_enabled: bool
