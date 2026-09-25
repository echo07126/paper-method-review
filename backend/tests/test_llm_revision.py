"""模型补写契约：必须结合全文、必须给出可核验原文出处，无依据不写。"""
import json
from pathlib import Path

from app.engine.revision import _document_blocks, _quote_exists, build_revised_document
from app.models.schemas import Anchor, DocumentIR, Finding, Paragraph, Severity, Verdict


class FakeProvider:
    """按预设 JSON 返回，用于验证校验逻辑（不访问网络）。"""

    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = 0
        self.last_messages: list[dict] = []

    def complete_structured(self, messages, temperature=0.0, max_tokens=None):
        self.calls += 1
        self.last_messages = messages

        class Result:
            content = json.dumps(self.payload, ensure_ascii=False)
            tokens = {"input": 0, "output": 0}

        return Result()

    def complete_text(self, messages, temperature=0.3, max_tokens=None):
        raise AssertionError("本模块不调用文本接口")


def _document() -> DocumentIR:
    return DocumentIR(
        source_name="demo.docx",
        parser="docx",
        parser_version="1",
        sections=[],
        paragraphs=[
            Paragraph(index=0, text="本研究纳入 1240 例眼底彩照，按 8:2 划分训练集与验证集。"),
            Paragraph(index=1, text="模型采用 ResNet-50，在验证集上 AUC 达 0.94。"),
        ],
    )


def _finding(item_id: str, index: int) -> Finding:
    return Finding(
        finding_id="F-" + item_id,
        checklist_item_id=item_id,
        verdict=Verdict.PROBLEM,
        severity=Severity.MID,
        headline=item_id + " 标题",
        anchors=[Anchor(paragraph_index=index)],
        suggestion="建议",
    )


def test_document_blocks_labels_paragraph_numbers() -> None:
    blocks = _document_blocks(_document())
    assert "[P0]" in blocks and "[P1]" in blocks


def test_quote_must_exist_in_document() -> None:
    document = _document()
    assert _quote_exists(document, "1240 例眼底彩照")
    assert not _quote_exists(document, "我们使用了 5000 例多中心数据")


def test_model_rewrite_requires_verifiable_evidence() -> None:
    document = _document()
    provider = FakeProvider(
        {
            "revisions": [
                {
                    "checklist_item_id": "R-03",
                    "text": "本研究按 8:2 划分训练集与验证集，并固定随机种子 42 以保证可复现。",
                    "reason": "",
                    "evidence": {"paragraph_index": 0, "quote": "按 8:2 划分训练集与验证集"},
                },
                {
                    "checklist_item_id": "R-14",
                    "text": "随机种子固定为 42。",
                    "reason": "",
                    "evidence": {"paragraph_index": 0, "quote": "文中并未提及的凭空依据"},
                },
            ]
        }
    )
    revised, status = build_revised_document(document, [_finding("R-03", 0), _finding("R-14", 0)], provider=provider)

    assert provider.calls == 1
    assert status["R-03"][0] == "rewritten"
    assert "8:2" in revised.paragraphs[0].text
    assert "依据段落 P0" in status["R-03"][1], "补写需附带可核验出处"
    assert status["R-14"][0] == "pending", "出处不实的补写必须被拒绝"
    assert "随机种子固定为 42" not in revised.paragraphs[0].text


def test_model_null_text_is_respected() -> None:
    document = _document()
    provider = FakeProvider(
        {
            "revisions": [
                {
                    "checklist_item_id": "R-09",
                    "text": None,
                    "reason": "原文未报告置信区间，需作者补充实际统计量。",
                    "evidence": None,
                }
            ]
        }
    )
    revised, status = build_revised_document(document, [_finding("R-09", 1)], provider=provider)
    assert status["R-09"][0] == "pending"
    assert status["R-09"][1].startswith("原文未报告置信区间")
    assert revised.paragraphs[1].text == document.paragraphs[1].text


def test_fallback_to_template_without_provider() -> None:
    document = _document()
    revised, status = build_revised_document(document, [_finding("R-03", 0)], provider=None)
    assert status["R-03"][0] == "rewritten"
    assert "规范句式" in status["R-03"][1], "无模型时必须标注来源为清单规范句式"
    assert "7:1:2" in revised.paragraphs[0].text


def test_compare_page_still_exposes_status() -> None:
    view = (
        Path(__file__).resolve().parents[2] / "frontend" / "src" / "views" / "CompareView.vue"
    ).read_text(encoding="utf-8")
    assert "revision_status" in view and "revision_note" in view
