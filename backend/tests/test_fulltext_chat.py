"""自由提问（全文问答）契约：全文注入、上下文上限与追问一致、可定位修改后展示。

背景：自由提问原先与追问共用一条路径，只带 finding 上下文，未注入全文，
「已读取全文并记忆」的口径无法成立；本轮改为全文注入并复用同一上下文上限。
"""
from pathlib import Path

from app.engine.qa_context import (
    build_question_context,
    build_qa_system_message,
    truncate_document_chunks,
)

ROOT = Path(__file__).resolve().parents[1]


def test_fulltext_truncation_keeps_whole_paragraphs() -> None:
    """全文超预算时按整段丢弃，不截半段，并标记发生截断。"""
    chunks = [f"段落{i}" + "字" * 20 for i in range(5)]
    kept, truncated = truncate_document_chunks(chunks, max_chars=60)
    assert truncated is True
    assert all(chunk in chunks for chunk in kept), "必须按整段边界保留，不得拼出半个段落"


def test_fulltext_context_marks_truncation() -> None:
    text = "\n".join(f"第{i}段" + "字" * 100 for i in range(6))
    context = build_question_context(text, max_chars=150)
    assert "省略部分内容" in context, "截断时应显式提示，避免模型以为读到了全文"


def test_fulltext_scope_guard_declares_data_block() -> None:
    """全文注入必须声明为 DATA（非指令），防止论文内指令影响模型。"""
    system = build_qa_system_message()
    assert "DATA" in system["content"]
    assert "忽略" in system["content"]


def test_fulltext_shares_history_limits_with_followup() -> None:
    """自由提问的上下文上限必须与追问一致（10 轮 / 8000 字符）。"""
    from app.core.config import Settings

    settings = Settings()
    source = (ROOT / "app" / "api" / "routes_chat.py").read_text(encoding="utf-8")
    assert settings.chat_history_max_turns == 10
    assert settings.chat_history_max_chars == 8000
    assert "chat_history_max_turns" in source and "chat_history_max_chars" in source


def test_report_page_drops_revision_preview() -> None:
    """修改后示范不再挂在报告页：示范内容改为在修改对比页落成修改稿正文。"""
    view = (ROOT.parent / "frontend" / "src" / "views" / "ReportView.vue").read_text(encoding="utf-8")
    listing = (ROOT.parent / "frontend" / "src" / "components" / "FindingList.vue").read_text(encoding="utf-8")

    assert "showRevision" not in view and "显示修改后" not in view, "报告页不应再保留「显示修改后」开关"
    assert "suggested_revision" not in listing, "报告页问题清单不应再直接展示修改后示范"
    assert "去修改对比" in view, "报告页需提供进入修改对比的入口"


def test_report_page_merges_detail_into_list() -> None:
    """详情需内联进问题清单（点击展开），不再单独占一栏。"""
    view = (ROOT.parent / "frontend" / "src" / "views" / "ReportView.vue").read_text(encoding="utf-8")
    listing = (ROOT.parent / "frontend" / "src" / "components" / "FindingList.vue").read_text(encoding="utf-8")
    drawer = (ROOT.parent / "frontend" / "src" / "components" / "ChatDrawer.vue").read_text(encoding="utf-8")

    assert "FindingDetail" not in view, "问题详情应内联进清单，不再单独占一栏"
    assert "修改建议" in listing, "清单展开后应展示修改建议"
    assert "追问这条" in listing
    assert "全文自由提问" in drawer and "追问这条问题" in drawer, "两种对话需有独立标题"
