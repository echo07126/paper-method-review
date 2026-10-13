from pathlib import Path

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.api.deps import get_store, resolve_session
from app.core.audit import audit
from app.core.config import get_settings
from app.engine.checklist import MIN_EXPECTED_ITEMS, load_checklist
from app.engine.llm_provider import build_provider
from app.engine.revision import review_and_compare
from app.models.schemas import DocumentIR, ReviewReport, TaskAccepted, Verdict
from app.tasks import submit

router = APIRouter(tags=["compare"])


class CompareRequest(BaseModel):
    before_report_id: str
    after_report_id: str | None = None
    # 生成修改稿需要模型结合全文写补写句，默认开启；显式传 false 则退回清单规范句式
    use_llm: bool | None = None


def _detail(finding, revision_status: dict[str, tuple[str, str]] | None = None) -> dict:
    """单条结论的对比视图。

    修改稿侧的结论必须带上逐条 `revision_status` / `revision_note`：前端据此区分
    「已自动改写」「需作者本人处理」「未自动改写」。此前该状态只被拼进 notes 散文，
    前端读不到字段，于是每条都退化成灰底「未自动改写」、且「仍有 N 项需人工处理」永不显示。
    """
    status, note = (revision_status or {}).get(finding.checklist_item_id, ("pending", ""))
    return {
        "checklist_item_id": finding.checklist_item_id,
        "headline": finding.headline,
        "severity": finding.severity,
        "certainty": finding.certainty,
        "verdict": finding.verdict,
        "anchors": [a.model_dump() for a in finding.anchors],
        "description": finding.description,
        "suggestion": finding.suggestion,
        "revision_status": status,
        "revision_note": note,
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


def _build_response(
    before: ReviewReport,
    after: ReviewReport,
    revision_status: dict[str, tuple[str, str]] | None = None,
    document_id: str | None = None,
) -> dict:
    before_problems = _problems(before)
    after_problems = _problems(after)
    resolved_ids = sorted(set(before_problems) - set(after_problems))
    new_ids = sorted(set(after_problems) - set(before_problems))
    kept_ids = sorted(set(before_problems) & set(after_problems))
    payload = {
        "before": before.counts,
        "after": after.counts,
        "resolved": resolved_ids,
        "new": new_ids,
        "kept": kept_ids,
        "before_findings": [_detail(f) for f in before.findings if f.verdict == Verdict.PROBLEM],
        "after_findings": [_detail(f, revision_status) for f in after.findings if f.verdict == Verdict.PROBLEM],
        "resolved_findings": [_detail(before_problems[i], revision_status) for i in resolved_ids],
        "new_findings": [_detail(after_problems[i], revision_status) for i in new_ids],
        "kept_findings": [_detail(after_problems[i], revision_status) for i in kept_ids],
    }
    # 修改稿的 document_id：前端据此把「修改后」原文栏切到修改稿，
    # 否则「回到报告」会把修改稿报告与未修改的原稿正文并排显示。
    if document_id:
        payload["document_id"] = document_id
    return payload


@router.post("/compare", response_model=TaskAccepted, status_code=202)
def compare(payload: CompareRequest, request: Request, response: Response) -> dict:
    """提交对比任务：没有修改稿报告时，用初稿报告里的示范改写生成修改稿并二次审查，再对比。

    这样右侧清单与原文都来自真实复审，而不是"假定已解决"的推算。
    立即 202，业务主体在任务线程池执行，前端轮询 /tasks/{id}。
    """
    store = get_store()
    session_id = resolve_session(request, response, store)
    # 快速失败校验：越权/不存在仍在 202 之前返回 404
    before = ReviewReport(**store.authorized_report(session_id, payload.before_report_id))
    after: ReviewReport | None = None
    document: DocumentIR | None = None
    if payload.after_report_id:
        after = ReviewReport(**store.authorized_report(session_id, payload.after_report_id))
    else:
        document_id = store.report_document_id(session_id, payload.before_report_id)
        document = DocumentIR(**store.authorized_document(session_id, document_id))

    def _run() -> dict:
        settings = get_settings()
        store = get_store()
        if after is not None:
            return _build_response(before, after)

        assert document is not None  # 由提交前的校验保证
        items = load_checklist(
            Path(settings.checklist_dir) / "quant-ai-v1.json", MIN_EXPECTED_ITEMS
        )
        provider = build_provider(settings)
        use_llm = settings.llm_default_enabled if payload.use_llm is None else payload.use_llm
        # 复用已取回的初稿报告，避免把同一篇初稿再审查一遍（省一次完整模型审查）。
        _, revised_report, revised_document, revision_status = review_and_compare(
            document,
            items,
            provider=provider,
            use_llm=use_llm and provider is not None,
            media_root=Path(settings.temp_dir) / session_id,
            before=before,
        )
        revised_report.notes = [
            *revised_report.notes,
            _revision_note(revision_status, use_llm and provider is not None),
        ]
        revised_document_id = store.save_document(
            session_id, revised_document.source_name, revised_document.model_dump_json()
        )
        store.save_report(session_id, revised_document_id, revised_report.report_id, revised_report.model_dump_json())
        audit("compare_autorevised", source_report_id=payload.before_report_id, revised_report_id=revised_report.report_id)
        return _build_response(before, revised_report, revision_status, revised_document_id)

    job_id = submit(
        "compare",
        session_id,
        {"before_report_id": payload.before_report_id, "after_report_id": payload.after_report_id},
        _run,
    )
    return {"task_id": job_id, "state": "queued", "kind": "compare", "poll_url": f"/tasks/{job_id}"}
