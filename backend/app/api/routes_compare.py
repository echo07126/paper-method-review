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
    # 生成修改稿需要模型结合全文写补写句，默认开启；显式传 false 则退回清单规范句式
    use_llm: bool | None = None


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


REVISION_NOTE = (
    "修改稿的补写内容由模型结合全文生成，每条均要求给出可核验的原文出处；"
    "未给出可用出处的条目不会被写入，仍列在修改稿清单中由作者处理。"
)
REVISION_NOTE_RULE = (
    "本次生成修改稿时未调用模型，补写内容来自清单的规范句式，需核对与本文实际数据是否一致。"
)


def _revision_note(status: dict[str, tuple[str, str]], used_llm: bool) -> str:
    counts = {"rewritten": 0, "manual": 0, "pending": 0}
    for state, _ in status.values():
        counts[state] = counts.get(state, 0) + 1
    detail = f"（自动补写 {counts['rewritten']} 条、需作者处理 {counts['manual'] + counts['pending']} 条）"
    return (REVISION_NOTE if used_llm else REVISION_NOTE_RULE) + detail


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
    use_llm = settings.llm_default_enabled if payload.use_llm is None else payload.use_llm
    _, after, revised_document, revision_status = review_and_compare(
        document,
        items,
        provider=provider,
        use_llm=use_llm and provider is not None,
        media_root=Path(settings.temp_dir) / session_id,
    )
    after.notes = [*after.notes, _revision_note(revision_status, use_llm and provider is not None)]
    revised_document_id = store.save_document(
        session_id, revised_document.source_name, revised_document.model_dump_json()
    )
    store.save_report(session_id, revised_document_id, after.report_id, after.model_dump_json())
    audit("compare_autorevised", source_report_id=payload.before_report_id, revised_report_id=after.report_id)
    return _build_response(before, after)
