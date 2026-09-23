"""报告历史页面契约：前端必须消费 /reports 的全部字段（历史页可用性回归）。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def frontend_text() -> str:
    chunks = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix in {".ts", ".vue"}:
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def test_history_route_and_view_exist() -> None:
    router = (FRONTEND_SRC / "router" / "index.ts").read_text(encoding="utf-8")
    assert 'name: "history"' in router, "缺少 history 路由"
    assert 'HistoryView' in router, "路由未引用 HistoryView"
    assert (FRONTEND_SRC / "views" / "HistoryView.vue").exists(), "缺少 HistoryView.vue"


def test_history_view_consumes_report_summary_fields() -> None:
    view = (FRONTEND_SRC / "views" / "HistoryView.vue").read_text(encoding="utf-8")
    for field in ("report_id", "document_name", "counts", "created_at"):
        assert field in view, f"历史页未使用 ReportSummary.{field}"
    # 列表数据来源必须是后端 /reports 接口
    assert "/reports" in view, "历史页未调用 GET /reports"


def test_history_entry_reachable_from_app_shell() -> None:
    app_shell = (FRONTEND_SRC / "App.vue").read_text(encoding="utf-8")
    assert "history" in app_shell, "顶栏没有报告历史入口"


def test_reports_summary_type_has_optional_document_name() -> None:
    """document_name 可能为 null，前端类型必须允许 null（否则运行时取字段报错）。"""
    types = (FRONTEND_SRC / "api" / "types.ts").read_text(encoding="utf-8")
    match = re.search(r"interface ReportSummary \{(.*?)\}", types, re.S)
    assert match, "未找到 ReportSummary 类型"
    assert "document_name" in match.group(1)
    assert "null" in match.group(1), "document_name 未声明可为 null"
