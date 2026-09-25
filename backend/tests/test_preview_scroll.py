"""契约测试：报告页点击问题后，右侧原文必须自动滚动到对应段落。

背景：ReportView 只把 highlight-index 传给 PaperPreview，PaperPreview 只做高亮、
没有滚动逻辑，导致「点问题→右侧定位」失效（mockup 原型里是有 scrollIntoView 的）。
本测试锁定：① 右侧容器可被引用；② 高亮变化会触发滚动；③ 滚动在 nextTick 后执行。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def _paper_preview_text() -> str:
    return (FRONTEND_SRC / "components" / "PaperPreview.vue").read_text(encoding="utf-8")


def test_preview_container_is_ref_addressable() -> None:
    text = _paper_preview_text()
    assert re.search(r'ref=\"\w+\"', text), "PaperPreview 缺少可引用的滚动容器 ref"
    assert "scrollTo" in text, "PaperPreview 缺少滚动定位逻辑（scrollTo）"


def test_highlight_change_triggers_scroll() -> None:
    text = _paper_preview_text()
    assert "watch" in text, "PaperPreview 未监听 highlightIndex 变化，点击问题不会触发滚动"
    assert "highlightIndex" in text, "PaperPreview 未使用 highlightIndex"


def test_scroll_runs_after_render() -> None:
    text = _paper_preview_text()
    assert "nextTick" in text, "滚动未在 nextTick 后执行，DOM 可能尚未渲染目标段落"


def test_report_view_passes_anchor_index() -> None:
    view = (FRONTEND_SRC / "views" / "ReportView.vue").read_text(encoding="utf-8")
    assert "highlight-index" in view, "ReportView 未把问题锚点传给 PaperPreview"
    assert "anchors[0]?.paragraph_index" in view, "ReportView 未取用锚点段落号"
