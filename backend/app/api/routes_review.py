from pathlib import Path

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.api.deps import get_store, resolve_session
from app.core.audit import audit
from app.core.config import get_settings
from app.engine.checklist import load_checklist
from app.engine.llm_provider import build_provider
from app.engine.reviewer import review_document
from app.models.schemas import DocumentIR, TaskAccepted
from app.tasks import submit

router = APIRouter(tags=["review"])


class ReviewRequest(BaseModel):
    document_id: str
    use_llm: bool | None = None
    demote_on_figures: bool | None = None


@router.post("/reviews", response_model=TaskAccepted, status_code=202)
def create_review(payload: ReviewRequest, request: Request, response: Response) -> dict:
    """提交结构化审查任务：立即 202，业务主体在任务线程池执行，前端轮询 /tasks/{id}。"""
    store = get_store()
    session_id = resolve_session(request, response, store)

    # 快速失败校验：越权/不存在仍在 202 之前返回 404
    document = DocumentIR(**store.authorized_document(session_id, payload.document_id))

    def _run() -> dict:
        # 配置与清单在任务体内读取，确保执行时用的是最新配置（而非提交瞬间的快照）。
        settings = get_settings()
        store = get_store()
        items = load_checklist(Path(settings.checklist_dir) / "quant-ai-v1.json")
        use_llm = settings.llm_default_enabled if payload.use_llm is None else payload.use_llm
        provider = build_provider(settings) if use_llm else None
        report = review_document(
            document,
            items,
            provider=provider,
            use_llm=use_llm,
            demote_on_figures=payload.demote_on_figures,
            media_root=Path(settings.temp_dir) / session_id,
        )
        store.save_report(session_id, payload.document_id, report.report_id, report.model_dump_json())
        audit("review_created", report_id=report.report_id, problems=report.counts.get("total", 0), use_llm=use_llm)
        return {
            "report_id": report.report_id,
            "counts": report.counts,
            "duration_ms": report.duration_ms,
            "tokens": report.tokens,
            "notes": report.notes,
            "figure_references": report.figure_references,
            "paper_type": report.paper_type,
            "demote_on_figures": report.demote_on_figures,
            "quality": report.quality,
        }

    job_id = submit("review", session_id, {"document_id": payload.document_id}, _run)
    return {"task_id": job_id, "state": "queued", "kind": "review", "poll_url": f"/tasks/{job_id}"}