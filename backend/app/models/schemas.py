from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Severity(str, Enum):
    HIGH = "high"
    MID = "mid"
    LOW = "low"


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
    headline: str
    description: str = ""
    evidence_elements: list[str] = Field(default_factory=list)
    anchors: list[Anchor] = Field(default_factory=list)
    suggestion: str = ""
    # 「修改后展示」：把建议落实为可直接对照的改写示例（可选展示，不参与问题判定）
    suggested_revision: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)


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


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

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


class ReportSummary(BaseModel):
    report_id: str
    document_id: str
    document_name: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    created_at: str


class CompareResponse(BaseModel):
    before: dict[str, int]
    after: dict[str, int]
    resolved: list[str]
    new: list[str]
    kept: list[str]


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
