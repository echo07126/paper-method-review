from pathlib import Path

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.api.deps import get_store, resolve_session
from app.core.audit import audit
from app.core.config import get_settings
from app.engine.checklist import load_checklist
from app.engine.llm_provider import build_provider
from app.engine.revision import review_and_compare
from app.models.schemas import CompareResponse, DocumentIR, ReviewReport, Verdict

router = APIRouter(tags=["compare"])


class CompareRequest(BaseModel):
    before_report_id: str
    after_report_id: str | None = None
    use_llm: bool = False


def _detail(finding) -> dict:
    return {
        "checklist_item_id": finding.checklist_item_id,
        "headline": finding.headline,
        "severity": finding.severity,
        "verdict": finding.verdict,
        "anchors": [a.model_dump() for a in finding.anchors],
        "description": finding.description,
        "suggestion": finding.suggestion,
    }


def _problems(report: ReviewReport) -> dict[str, object]:
    return {f.checklist_item_id: f for f in report.findings if f.verdict == Verdict.PROBLEM}


def _build_response(before: ReviewReport, after: ReviewReport) -> dict:
    before_problems = _problems(before)
    after_problems = _problems(after)
    resolved_ids = sorted(set(before_problems) - set(after_problems))
    new_ids = sorted(set(after_problems) - set(before_problems))
    kept_ids = sorted(set(before_problems) & set(after_problems))
    return {
        "before": before.counts,
        "after": after.counts,
        "resolved": resolved_ids,
        "new": new_ids,
        "kept": kept_ids,
        "before_findings": [_detail(f) for f in before.findings if f.verdict == Verdict.PROBLEM],
        "after_findings": [_detail(f) for f in after.findings if f.verdict == Verdict.PROBLEM],
        "resolved_findings": [_detail(before_problems[i]) for i in resolved_ids],
        "new_findings": [_detail(after_problems[i]) for i in new_ids],
        "kept_findings": [_detail(after_problems[i]) for i in kept_ids],
    }


@router.post("/compare", response_model=CompareResponse)
def compare(payload: CompareRequest, request: Request, response: Response) -> dict:
    """没有修改稿报告时，用初稿报告里的示范改写生成修改稿并二次审查，再对比。

    这样右侧清单与原文都来自真实复审，而不是"假定已解决"的推算。
    """
    settings = get_settings()
    store = get_store()
    session_id = resolve_session(request, response, store)
    before = ReviewReport(**store.authorized_report(session_id, payload.before_report_id))

    if payload.after_report_id:
        after = ReviewReport(**store.authorized_report(session_id, payload.after_report_id))
        return _build_response(before, after)

    document_id = store.report_document_id(session_id, payload.before_report_id)
    document = DocumentIR(**store.authorized_document(session_id, document_id))
    items = load_checklist(Path(settings.checklist_dir) / "quant-ai-v1.json")
    provider = build_provider(settings)
    _, after, revised_document, _ = review_and_compare(
        document,
        items,
        provider=provider,
        use_llm=payload.use_llm and provider is not None,
        media_root=Path(settings.temp_dir) / session_id,
    )
    revised_document_id = store.save_document(
        session_id, revised_document.source_name, revised_document.model_dump_json()
    )
    store.save_report(session_id, revised_document_id, after.report_id, after.model_dump_json())
    audit("compare_autorevised", source_report_id=payload.before_report_id, revised_report_id=after.report_id)
    return _build_response(before, after)
