from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.api.deps import get_store, resolve_session
from app.models.schemas import CompareResponse, ReviewReport, Verdict

router = APIRouter(tags=["compare"])


class CompareRequest(BaseModel):
    before_report_id: str
    after_report_id: str


@router.post("/compare", response_model=CompareResponse)
def compare(payload: CompareRequest, request: Request, response: Response) -> dict:
    store = get_store()
    session_id = resolve_session(request, response, store)
    before = ReviewReport(**store.authorized_report(session_id, payload.before_report_id))
    after = ReviewReport(**store.authorized_report(session_id, payload.after_report_id))

    def problems(report: ReviewReport) -> list:
        return [f for f in report.findings if f.verdict == Verdict.PROBLEM]

    before_problems = {f.checklist_item_id: f for f in problems(before)}
    after_problems = {f.checklist_item_id: f for f in problems(after)}

    def detail(finding) -> dict:
        return {
            "checklist_item_id": finding.checklist_item_id,
            "headline": finding.headline,
            "severity": finding.severity,
            "verdict": finding.verdict,
            "anchors": [a.model_dump() for a in finding.anchors],
            "description": finding.description,
            "suggestion": finding.suggestion,
            "suggested_revision": finding.suggested_revision,
        }

    resolved_ids = sorted(set(before_problems) - set(after_problems))
    new_ids = sorted(set(after_problems) - set(before_problems))
    kept_ids = sorted(set(before_problems) & set(after_problems))
    return {
        "before": before.counts,
        "after": after.counts,
        "resolved": resolved_ids,
        "new": new_ids,
        "kept": kept_ids,
        "before_findings": [detail(f) for f in before.findings if f.verdict == Verdict.PROBLEM],
        "after_findings": [detail(f) for f in after.findings if f.verdict == Verdict.PROBLEM],
        "resolved_findings": [detail(before_problems[i]) for i in resolved_ids],
        "new_findings": [detail(after_problems[i]) for i in new_ids],
        "kept_findings": [detail(after_problems[i]) for i in kept_ids],
    }
