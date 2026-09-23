"""W2 验证：真实调用 deepseek-flash 跑结构化审查，并检查证据门控与降级。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.engine.checklist import load_checklist  # noqa: E402
from app.engine.llm_provider import build_provider  # noqa: E402
from app.engine.reviewer import review_document  # noqa: E402
from app.models.schemas import DocumentIR, Paragraph, Section  # noqa: E402

TEXT = [
    "本研究纳入 1,240 例眼底彩照，按 8:2 划分为训练集与验证集。",
    "超参数在验证集上通过网格搜索确定，最终在测试集上评估。",
    "结果显示准确率为 0.912，较基线提升 2.1 个百分点（p<0.05）。",
    "本文提出了一种改进的注意力机制模块，可推广至各类医疗影像场景。",
]


def build_document() -> DocumentIR:
    paragraphs = [Paragraph(index=i, text=text) for i, text in enumerate(TEXT)]
    return DocumentIR(
        source_name="llm_review_demo.docx",
        parser="synthetic",
        parser_version="0",
        sections=[Section(id="sec_1", title="2. 方法", level=1, paragraph_index=0)],
        paragraphs=paragraphs,
    )


def main() -> int:
    settings = get_settings()
    provider = build_provider(settings)
    if provider is None:
        print("FAIL: 未配置模型服务（检查 backend/.env）")
        return 2
    print("model:", settings.deepseek_model)

    items = load_checklist(ROOT / "checklists" / "quant-ai-v1.json")
    report = review_document(build_document(), items, provider=provider, use_llm=True)

    print("counts:", report.counts)
    print("tokens:", report.tokens, "duration_ms:", report.duration_ms)
    print("notes:", report.notes or "无")
    print("findings:")
    for finding in report.findings:
        engine = finding.provenance.get("engine")
        gate = finding.provenance.get("evidence_gate", "-")
        print(f"  [{engine}/{gate}] {finding.checklist_item_id} {finding.severity.value} {finding.headline}")

    engines = {finding.provenance.get("engine") for finding in report.findings}
    if "llm" not in engines:
        print("WARN: 本次未产生 LLM 判定（可能被证据门控或模型返回空）")
    print("LLM REVIEW CHECK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
