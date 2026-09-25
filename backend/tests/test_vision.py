"""L3 图像内容识读：多模态 content 构造、图内数值回填与优雅降级（P2-3 / 需求 15.5.1）。"""
import base64
import json
from pathlib import Path

from docx import Document
from docx.shared import Inches

from app.core.config import Settings
from app.engine.checklist import load_checklist
from app.engine.llm_provider import LLMResult, LLMUnavailable
from app.engine.reviewer import review_document
from app.engine.vision import ITEM_ID, read_figure_values
from app.models.schemas import DocumentIR, ImageRef, Anchor, Verdict
from app.parsers.registry import parse_document
from app.storage.files import save_upload

ROOT = Path(__file__).resolve().parents[2]
# 1x1 透明 PNG（最小合法图像，避免测试依赖二进制夹具）
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


class VisionProvider:
    """返回图内数值线索；system 含「插图」时才走识读分支。"""

    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload if payload is not None else {"values": ["准确率 0.91", "n=42"], "concern": None}
        self.calls: list[list[dict]] = []

    def complete_structured(self, messages, temperature: float = 0.0):
        self.calls.append(messages)
        return LLMResult(
            content=json.dumps(self.payload), model="vision-fake", tokens={"input": 11, "output": 7}, retries=0, duration_ms=1
        )

    def complete_text(self, messages, temperature: float = 0.3):
        raise LLMUnavailable("vision test provider 不提供自由文本")


class BrokenProvider(VisionProvider):
    def complete_structured(self, messages, temperature: float = 0.0):
        raise LLMUnavailable("模型不可用（模拟）")


def _document_with_image(tmp_path: Path, name: str = "fig.docx") -> DocumentIR:
    source = tmp_path / name
    doc = Document()
    doc.add_heading("3. 结果", level=1)
    doc.add_paragraph("如图1所示，模型性能显著优于基线。")
    doc.add_picture(str(_png(tmp_path)), width=Inches(1))
    doc.add_paragraph("图1 模型准确率对比")
    doc.save(source)
    return parse_document(source, source.name, None)


def _png(tmp_path: Path) -> Path:
    path = tmp_path / "dot.png"
    if not path.exists():
        path.write_bytes(PNG_1x1)
    return path


def test_image_is_saved_and_anchored(tmp_path: Path) -> None:
    """内嵌图片必须落盘（供识读）并带上文档流锚点与题注。"""
    document = _document_with_image(tmp_path)
    assert len(document.images) == 1
    image = document.images[0]
    assert image.byte_size > 0
    assert image.caption.startswith("图1"), "应关联到紧邻图片下方的题注"
    assert (tmp_path / image.filename).exists(), "图片应已落盘"
    assert document.meta.get("image_saved") == 1
    assert document.parser_version == "1.3"


def test_multimodal_content_is_constructed(tmp_path: Path) -> None:
    """多模态请求必须是 text + image_url(content 数组)，且图片为 base64 data URL。"""
    document = _document_with_image(tmp_path)
    provider = VisionProvider()
    findings, tokens = read_figure_values(document, provider, tmp_path)

    assert len(findings) == 1
    content = provider.calls[0][1]["content"]
    assert isinstance(content, list), "多模态 content 必须是数组"
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert tokens == {"input": 11, "output": 7}


def test_vision_finding_is_advisory_and_anchored(tmp_path: Path) -> None:
    """图内数值线索必须为「存疑」并挂在图片锚点上，不计入问题数。"""
    document = _document_with_image(tmp_path)
    findings, _ = read_figure_values(document, VisionProvider(), tmp_path)

    finding = findings[0]
    assert finding.checklist_item_id == ITEM_ID
    assert finding.verdict == Verdict.UNCERTAIN
    assert finding.anchors[0].paragraph_index == document.images[0].anchor.paragraph_index
    assert finding.provenance.get("evidence_gate") == "vision_read"
    assert finding.provenance.get("advisory") is True
    assert "准确率 0.91" in finding.description


def test_missing_media_file_is_skipped(tmp_path: Path) -> None:
    """图片文件缺失时静默跳过，不抛错、不产生结论、不消耗 token。"""
    document = _document_with_image(tmp_path)
    for image in document.images:
        (tmp_path / image.filename).unlink()

    findings, tokens = read_figure_values(document, VisionProvider(), tmp_path)
    assert findings == []
    assert tokens == {"input": 0, "output": 0}


def test_provider_unavailable_degrades_silently(tmp_path: Path) -> None:
    """模型不可用时不抛异常（优雅降级），返回空结论且无 token 计费。"""
    document = _document_with_image(tmp_path)
    findings, tokens = read_figure_values(document, BrokenProvider(), tmp_path)
    assert findings == []
    assert tokens == {"input": 0, "output": 0}


def test_no_images_or_media_root_returns_empty() -> None:
    empty = ([], {"input": 0, "output": 0})
    document = DocumentIR(source_name="x.docx", parser="docx", parser_version="1.3")
    provider = VisionProvider()
    assert read_figure_values(document, provider, None) == empty
    document.images.append(
        ImageRef(id="img_1", index=0, media_type="image/png", byte_size=10, filename="m/fig1.png", anchor=Anchor(paragraph_index=0))
    )
    assert read_figure_values(document, provider, "/tmp/nowhere") == empty
    assert read_figure_values(document, provider, "/tmp/nowhere", max_images=0) == empty


def test_review_document_collects_vision_tokens(tmp_path: Path) -> None:
    """审查链路：启用模型顾问时识读图片并把 token 计入报告。"""
    document = _document_with_image(tmp_path)
    items = load_checklist(ROOT / "checklists" / "quant-ai-v1.json")
    provider = VisionProvider()

    report = review_document(
        document, items, provider=provider, use_llm=True, demote_on_figures=False, media_root=tmp_path
    )

    vision = [f for f in report.findings if f.checklist_item_id == ITEM_ID]
    assert vision, "应回填图内数值线索"
    assert vision[0].verdict == Verdict.UNCERTAIN
    assert report.tokens["input"] >= 11 and report.tokens["output"] >= 7
    assert any("识读" in note for note in report.notes)


def test_vision_disabled_keeps_rule_only_behaviour(tmp_path: Path) -> None:
    """未启用模型顾问时不触发识读（规则模式零额外调用）。"""
    document = _document_with_image(tmp_path)
    items = load_checklist(ROOT / "checklists" / "quant-ai-v1.json")
    provider = VisionProvider()

    report = review_document(document, items, provider=None, use_llm=False, media_root=tmp_path)

    assert not [f for f in report.findings if f.checklist_item_id == ITEM_ID]
    assert provider.calls == []
    assert Settings().llm_vision_max_images == 4


def test_upload_places_media_inside_session_dir(tmp_path: Path) -> None:
    """图片落盘必须在会话临时目录内，才能被 purge_session_files 一并清除。"""
    source = tmp_path / "sess_source.docx"
    doc = Document()
    doc.add_heading("3. 结果", level=1)
    doc.add_paragraph("如图1所示。")
    doc.add_picture(str(_png(tmp_path)), width=Inches(1))
    doc.save(source)

    temp_dir = tmp_path / "tmp"
    saved = save_upload(str(temp_dir), "sess_vision", "fig.docx", source.read_bytes(), 50)
    document = parse_document(saved, "fig.docx", None)

    assert document.images, "上传解析后应有图片"
    for image in document.images:
        resolved = (saved.parent / image.filename).resolve()
        assert str(resolved).startswith(str((temp_dir / "sess_vision").resolve())), "图片必须落在会话目录内"
