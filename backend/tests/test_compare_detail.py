"""修改对比页契约：逐条明细字段与双栏渲染所需的锚点。"""
from pathlib import Path

from app.models.schemas import CompareResponse, ReviewReport, Verdict


def test_compare_response_exposes_finding_details() -> None:
    """对比接口需返回逐条明细，供双栏问题清单直接渲染（不依赖前端再取报告）。"""
    fields = CompareResponse.model_fields
    for name in (
        "before_findings",
        "after_findings",
        "resolved_findings",
        "new_findings",
        "kept_findings",
    ):
        assert name in fields, f"对比响应缺少 {name}"


def test_compare_detail_keeps_anchor_for_locating() -> None:
    """明细必须保留 anchors，否则对比页无法定位到原文段落。"""
    from app.api.routes_compare import compare  # noqa: F401  (import 检查)

    source = (Path(__file__).resolve().parents[1] / "app" / "api" / "routes_compare.py").read_text(encoding="utf-8")
    assert "anchors" in source
    assert "Verdict.PROBLEM" in source, "对比明细应只包含需要修改的问题条目"


def test_compare_view_renders_two_sided_lists() -> None:
    """前端对比页需按原型渲染左右两栏：问题清单 + 原文定位。"""
    view = (
        Path(__file__).resolve().parents[2] / "frontend" / "src" / "views" / "CompareView.vue"
    ).read_text(encoding="utf-8")
    assert "before_findings" in view and "after_findings" in view
    assert "PaperPreview" in view, "两侧都需嵌原文预览以支持定位"
    assert "delta-banner" in view, "缺少问题增减汇总条"


def test_upload_and_parse_follow_mockup_layout() -> None:
    """上传页/解析页需对齐原型：拖拽上传 + 章节大纲 + 原文两栏。"""
    root = Path(__file__).resolve().parents[2] / "frontend" / "src" / "views"
    upload = (root / "UploadView.vue").read_text(encoding="utf-8")
    parse = (root / "ParseView.vue").read_text(encoding="utf-8")

    assert "dropzone" in upload and "flow-mini" in upload and "privacy-note" in upload
    assert "outline-item" in parse and "sectionRange" in parse
    assert "PaperPreview" not in parse or "data-paragraph-index" in parse


def test_compare_view_locate_uses_rendered_anchor() -> None:
    """对比页定位必须基于 PaperPreview 渲染出的段落锚点，且两栏原文直接展开（无内滚）。"""
    view = (
        Path(__file__).resolve().parents[2] / "frontend" / "src" / "views" / "CompareView.vue"
    ).read_text(encoding="utf-8")
    paper = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "components"
        / "PaperPreview.vue"
    ).read_text(encoding="utf-8")

    assert "data-paragraph-index" in view, "定位需按锚点查 DOM"
    assert "window.scrollTo" in view, "两栏原文共同参与同一页滚动"
    assert "max-height: 58vh" not in view and "paper-scroll" not in view, "取消内滚容器，避免内容显示不全"
    assert "externalScroll" in paper, "外部统一滚动时组件不得抢占滚动"
