from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import get_store, resolve_session
from app.core.config import get_settings
from app.engine.llm_provider import LLMUnavailable, build_provider
from app.engine.prompts import SYSTEM_GUARD
from app.models.schemas import ChatResponse, ReviewReport

router = APIRouter(tags=["chat"])

FALLBACK_TEMPLATE = (
    "【规则模板回复】请对照该条问题的原文位置检查：\n"
    "1) 是否描述了相应的研究设计或统计假设；\n"
    "2) 是否报告了必要的统计量（样本量、效应量、置信区间）；\n"
    "3) 是否说明了该结论的适用范围与局限。\n"
    "配置模型服务后可获得针对该句的具体改写建议。"
)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    finding_id: str | None = None


@router.post("/reports/{report_id}/chat", response_model=ChatResponse)
def chat(report_id: str, payload: ChatRequest, request: Request, response: Response) -> dict:
    settings = get_settings()
    store = get_store()
    session_id = resolve_session(request, response, store)
    report = ReviewReport(**store.authorized_report(session_id, report_id))

    finding = next((f for f in report.findings if f.finding_id == payload.finding_id), None)
    context = ""
    if finding:
        context = f"问题：{finding.headline}\n说明：{finding.description}\n建议：{finding.suggestion}"

    provider = build_provider(settings)
    if provider is None:
        return {"answer": FALLBACK_TEMPLATE, "source": "fallback", "note": "未配置模型服务，已使用规则模板回复（FR-D5）。"}

    messages = [
        {"role": "system", "content": SYSTEM_GUARD + "\n请用简洁的中文回答，给出可操作的修改建议。"},
        {"role": "user", "content": f"针对以下审查问题回答用户提问。\n{context}\n\n用户问题：{payload.question}"},
    ]
    try:
        result = provider.complete_text(messages)
        return {"answer": result.content, "source": "llm", "tokens": result.tokens}
    except LLMUnavailable as exc:
        return {"answer": FALLBACK_TEMPLATE, "source": "fallback", "note": f"模型暂不可用：{exc}"}
