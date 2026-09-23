"""为全部接口补 response_model（DTO），并保持路由实现不变。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "backend" / "app" / "api"
SCHEMAS = ROOT / "backend" / "app" / "models" / "schemas.py"

# 1) 追加 DTO
dto = '''

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


class ChatResponse(BaseModel):
    answer: str
    source: Literal["llm", "fallback"]
    tokens: dict[str, int] | None = None
    note: str | None = None


class PurgeResponse(BaseModel):
    status: str


class HealthResponse(BaseModel):
    status: str
    app_env: str
    docs_enabled: bool
'''
text = SCHEMAS.read_text(encoding="utf-8")
if "class HealthResponse" not in text:
    text = text.replace("from typing import Any", "from typing import Any, Literal")
    SCHEMAS.write_text(text.rstrip() + dto, encoding="utf-8")
    print("schemas.py 已追加 DTO")
else:
    print("schemas.py 已含 DTO，跳过")

# 2) 逐文件声明 response_model
PATCHES = {
    "routes_health.py": [
        ("from app.core.config import get_settings", "from app.core.config import get_settings\nfrom app.models.schemas import HealthResponse"),
        ('@router.get("/health")', '@router.get("/health", response_model=HealthResponse)'),
    ],
    "routes_upload.py": [
        ("from app.storage.files import save_upload", "from app.models.schemas import UploadResponse\nfrom app.storage.files import save_upload"),
        ('@router.post("/uploads")', '@router.post("/uploads", response_model=UploadResponse)'),
    ],
    "routes_document.py": [
        ("from app.api.deps import get_store, resolve_session", "from app.api.deps import get_store, resolve_session\nfrom app.models.schemas import DocumentResponse"),
        ('@router.get("/documents/{document_id}")', '@router.get("/documents/{document_id}", response_model=DocumentResponse)'),
    ],
    "routes_review.py": [
        ("from app.models.schemas import DocumentIR", "from app.models.schemas import DocumentIR, ReviewCreateResponse"),
        ('@router.post("/reviews")', '@router.post("/reviews", response_model=ReviewCreateResponse)'),
    ],
    "routes_report.py": [
        ("from app.models.schemas import ReviewReport", "from app.models.schemas import ReportSummary, ReviewReport"),
        ('@router.get("/reports")', '@router.get("/reports", response_model=list[ReportSummary])'),
        ('@router.get("/reports/{report_id}")', '@router.get("/reports/{report_id}", response_model=ReviewReport)'),
    ],
    "routes_chat.py": [
        ("from app.models.schemas import ReviewReport", "from app.models.schemas import ChatResponse, ReviewReport"),
        ('@router.post("/reports/{report_id}/chat")', '@router.post("/reports/{report_id}/chat", response_model=ChatResponse)'),
    ],
    "routes_compare.py": [
        ("from app.models.schemas import ReviewReport", "from app.models.schemas import CompareResponse, ReviewReport"),
        ('@router.post("/compare")', '@router.post("/compare", response_model=CompareResponse)'),
    ],
    "routes_session.py": [
        ("from app.storage.files import purge_session_files", "from app.models.schemas import PurgeResponse\nfrom app.storage.files import purge_session_files"),
        ('@router.post("/sessions/purge")', '@router.post("/sessions/purge", response_model=PurgeResponse)'),
    ],
}

for filename, pairs in PATCHES.items():
    path = API / filename
    content = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if old in content:
            content = content.replace(old, new)
        else:
            print(f"  [skip] {filename}: 未找到 -> {old[:40]}")
    path.write_text(content, encoding="utf-8")
    print(f"patched {filename}")
