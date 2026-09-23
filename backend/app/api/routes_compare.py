from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.api.deps import get_store, resolve_session
from app.models.schemas import CompareResponse, ReviewReport

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

    before_ids = {f.checklist_item_id for f in before.findings}
    after_ids = {f.checklist_item_id for f in after.findings}
    return {
        "before": before.counts,
        "after": after.counts,
        "resolved": sorted(before_ids - after_ids),
        "new": sorted(after_ids - before_ids),
        "kept": sorted(before_ids & after_ids),
    }
