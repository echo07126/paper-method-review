from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

from app.api.deps import get_store, resolve_session
from app.core.audit import audit
from app.core.config import get_settings
from app.engine.checklist import MIN_EXPECTED_ITEMS, load_checklist
from app.engine.llm_provider import build_provider
from app.engine.revision import review_and_compare
from app.models.schemas import DocumentIR, ReportSummary, ReviewReport, TaskAccepted
from app.reports.exporter import MarkdownExporter
from app.tasks import submit

router = APIRouter(tags=["reports"])

REVISION_NOTE_TEMPLATE = (
    "修改稿由报告中的示范改写落到对应段落生成，并重新执行了完整审查；"
    "结论依赖图表/原始数据/外部材料的条目不会自动改写，仍需作者确认。"
)


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


@router.post("/reports/{report_id}/revision", response_model=TaskAccepted, status_code=202)
def revise_report(report_id: str, request: Request, response: Response) -> dict:
    """提交「生成修改稿」任务：按报告中的示范改写生成修改稿，并对修改稿重新做一次完整审查。

    修改稿的 ReviewReport（左侧问题清单来自二次审查的真实结果）作为 result 返回，
    "解决 / 仍保留"也据此计算，不做任何"假定已解决"的推算。
    立即 202，业务主体在任务线程池执行，前端轮询 /tasks/{id}。
    """
    store = get_store()
    session_id = resolve_session(request, response, store)
    # 快速失败校验：越权/不存在仍在 202 之前返回 404
    stored_report = ReviewReport(**store.authorized_report(session_id, report_id))
    document_id = store.report_document_id(session_id, report_id)
    document = DocumentIR(**store.authorized_document(session_id, document_id))

    def _run() -> dict:
        settings = get_settings()
        store = get_store()
        items = load_checklist(
            Path(settings.checklist_dir) / "quant-ai-v1.json", MIN_EXPECTED_ITEMS
        )
        provider = build_provider(settings)
        # 复用已取回的初稿报告，避免重跑一次完整审查。
        _, revised_report, revised_document, _ = review_and_compare(
            document,
            items,
            provider=provider,
            use_llm=provider is not None,
            media_root=Path(settings.temp_dir) / session_id,
            before=stored_report,
        )
        revised_document_id = store.save_document(
            session_id, revised_document.source_name, revised_document.model_dump_json()
        )
        store.save_report(session_id, revised_document_id, revised_report.report_id, revised_report.model_dump_json())
        audit("report_revised", source_report_id=report_id, revised_report_id=revised_report.report_id)
        # 附带修改稿的 document_id：前端据此把原文栏切到修改稿正文，避免报告与正文错配。
        return {**revised_report.model_dump(), "document_id": revised_document_id}

    job_id = submit("revision", session_id, {"report_id": report_id}, _run)
    return {"task_id": job_id, "state": "queued", "kind": "revision", "poll_url": f"/tasks/{job_id}"}
