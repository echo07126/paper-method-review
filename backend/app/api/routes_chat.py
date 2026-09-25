from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import get_store, resolve_session
from app.core.config import get_settings
from app.engine.chat_history import build_chat_messages
from app.engine.llm_provider import LLMUnavailable, build_provider
from app.models.schemas import ChatMessage, ChatResponse, ReviewReport

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
    # 客户端可携带本地上文；服务端以落库历史为准，仅在落库为空时采用（如会话数据已被清理）
    history: list[ChatMessage] = Field(default_factory=list)


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
    question = f"针对以下审查问题回答用户提问。\n{context}\n\n用户问题：{payload.question}"

    keep = settings.chat_history_max_turns * 2
    stored = store.list_chat_messages(session_id, report_id)
    if not stored and payload.history:
        stored = [message.model_dump() for message in payload.history]

    messages, truncated = build_chat_messages(
        stored,
        question,
        max_turns=settings.chat_history_max_turns,
        max_chars=settings.chat_history_max_chars,
    )

    provider = build_provider(settings)
    if provider is None:
        answer, source, tokens, note = (
            FALLBACK_TEMPLATE,
            "fallback",
            None,
            "未配置模型服务，已使用规则模板回复（FR-D5）。",
        )
    else:
        try:
            result = provider.complete_text(messages)
            answer, source, tokens, note = result.content, "llm", result.tokens, None
        except LLMUnavailable as exc:
            answer, source, tokens, note = FALLBACK_TEMPLATE, "fallback", None, f"模型暂不可用：{exc}"

    store.append_chat_message(session_id, report_id, "user", payload.question, keep)
    store.append_chat_message(session_id, report_id, "assistant", answer, keep)

    return {
        "answer": answer,
        "source": source,
        "tokens": tokens,
        "note": note,
        "session_id": session_id,
        "history": store.list_chat_messages(session_id, report_id),
        "truncated": truncated,
    }
