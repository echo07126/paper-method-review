"""修改稿生成与二次审查契约。

要求：示范改写落到正文对应段落，修改稿重新走完整审查管线（左侧清单来自真实复审），
图表/数据依赖的条目不得被自动"改好"。
"""
from pathlib import Path

from app.engine.revision import MANUAL_ITEM_IDS, STRUCTURAL_ITEM_IDS, build_revised_document
from app.models.schemas import Anchor, DocumentIR, Finding, Paragraph, Severity, Verdict


def _document() -> DocumentIR:
    return DocumentIR(
        source_name="demo.docx",
        parser="docx",
        parser_version="1",
        paragraphs=[
            Paragraph(index=0, text="摘要：本文研究眼底图像分类。"),
            Paragraph(index=1, text="方法：采用 ResNet-50 训练模型。"),
        ],
    )


def _finding(item_id: str, paragraph_index: int | None, revision: str) -> Finding:
    """构造 finding；revision 仅用于断言补写文本来源，Finding 本身不再携带该字段。"""
    anchors = [Anchor(paragraph_index=paragraph_index)] if paragraph_index is not None else []
    suggestion = "建议" + (f"｜{revision}" if revision else "")
    return Finding(
        finding_id="F-" + item_id,
        checklist_item_id=item_id,
        verdict=Verdict.PROBLEM,
        severity=Severity.MID,
        headline=item_id + " 标题",
        anchors=anchors,
        suggestion=suggestion,
    )


def test_revision_is_written_into_matching_paragraph() -> None:
    document = _document()
    findings = [_finding("R-03", 1, "按 7:1:2 划分训练/验证/独立测试集，随机种子固定为 42。")]
    revised, status = build_revised_document(document, findings)

    assert status["R-03"][0] == "rewritten"
    assert "7:1:2" in revised.paragraphs[1].text
    # 原句必须保留，示范作为补写追加，避免破坏已满足的内容
    assert "ResNet-50" in revised.paragraphs[1].text
    # 段落索引不变，两侧清单段落号才可直接对照
    assert [p.index for p in revised.paragraphs] == [p.index for p in document.paragraphs]


def test_image_dependent_items_are_not_auto_rewritten() -> None:
    document = _document()
    findings = [_finding("R-05", 1, "为注意力模块做有/无消融实验。")]
    revised, status = build_revised_document(document, findings)

    assert status["R-05"][0] == "manual"
    assert "消融" not in revised.paragraphs[1].text, "依赖实验数据的条目不得伪造进正文"


def test_structural_reference_items_are_manual() -> None:
    document = _document()
    findings = [_finding("R-REF-01", 0, "补齐文末参考文献条目。")]
    _, status = build_revised_document(document, findings)
    assert status["R-REF-01"][0] == "manual"


def test_revision_status_covers_all_three_kinds() -> None:
    document = _document()
    findings = [
        _finding("R-03", 1, "补写划分说明。"),
        _finding("R-10", 1, "报告 5 次运行均值±标准差。"),
        _finding("R-04", None, ""),
    ]
    _, status = build_revised_document(document, findings)
    assert status["R-03"][0] == "rewritten"
    assert status["R-10"][0] == "manual"
    assert status["R-04"][0] == "pending", "无锚点且无补写文本时不得伪造成已改写"
    assert MANUAL_ITEM_IDS and STRUCTURAL_ITEM_IDS


def test_compare_endpoint_can_auto_revise() -> None:
    """对比页在没有修改稿报告时，由后端生成修改稿并二次审查。"""
    source = (
        Path(__file__).resolve().parents[1] / "app" / "api" / "routes_compare.py"
    ).read_text(encoding="utf-8")
    assert "review_and_compare" in source
    assert "after_report_id" in source, "仍需支持显式传入两份报告做对比"


def test_compare_view_exposes_revision_status() -> None:
    view = (
        Path(__file__).resolve().parents[2] / "frontend" / "src" / "views" / "CompareView.vue"
    ).read_text(encoding="utf-8")
    assert "revision_status" in view
    assert "需作者确认" in view, "右侧清单需显式标出图表/数据依赖的未解决条目"
