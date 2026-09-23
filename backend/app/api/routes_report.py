from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

from app.api.deps import get_store, resolve_session
from app.core.audit import audit
from app.models.schemas import ReportSummary, ReviewReport
from app.reports.exporter import MarkdownExporter

router = APIRouter(tags=["reports"])


@router.get("/reports", response_model=list[ReportSummary])
def list_reports(request: Request, response: Response) -> list[dict]:
    store = get_store()
    session_id = resolve_session(request, response, store)
    return store.list_reports(session_id)


@router.get("/reports/{report_id}", response_model=ReviewReport)
def get_report(report_id: str, request: Request, response: Response) -> dict:
    store = get_store()
    session_id = resolve_session(request, response, store)
    return store.authorized_report(session_id, report_id)


@router.get("/reports/{report_id}/export", response_class=PlainTextResponse)
def export_report(report_id: str, request: Request, response: Response, format: str = "markdown") -> str:
    store = get_store()
    session_id = resolve_session(request, response, store)
    report = ReviewReport(**store.authorized_report(session_id, report_id))
    audit("report_export", report_id=report_id, format=format)
    if format != "markdown":
        return "# 暂仅支持 Markdown 导出（PDF 导出在后续任务）\n"
    return MarkdownExporter().render(report)
