"""盲测：对指定论文跑规则（可选 LLM）审查，打印判定与锚点，便于人工核对。"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.engine.checklist import load_checklist  # noqa: E402
from app.engine.llm_provider import build_provider  # noqa: E402
from app.engine.reviewer import review_document  # noqa: E402
from app.parsers.registry import parse_document  # noqa: E402

# 默认使用改写脱敏样本；raw/ 下为用户提供的原始论文（非开放许可），不入库。
DOC = ROOT / "samples" / "real" / "blind-001.docx"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--doc", default=str(DOC))
    args = parser.parse_args()

    path = Path(args.doc)
    document = parse_document(path, path.name, None)
    items = load_checklist(ROOT / "checklists" / "quant-ai-v1.json")
    provider = build_provider(get_settings()) if args.llm else None
    report = review_document(document, items, provider=provider, use_llm=args.llm)

    print("=== 解析 ===")
    print(f"章节 {len(document.sections)} | 段落 {len(document.paragraphs)} | 图表 {document.meta.get('image_count')}图/{document.meta.get('table_count')}表 | 角标 {len(document.citations)} | 文献 {len(document.references)}")
    for warning in document.warnings:
        print("  警告:", warning)
    print("=== 判定 ===")
    print("counts:", report.counts)
    for finding in sorted(report.findings, key=lambda f: (f.verdict.value, f.checklist_item_id)):
        anchor = finding.anchors[0].paragraph_index if finding.anchors else "-"
        engine = finding.provenance.get("engine")
        print(f"  [{finding.verdict.value:<6}][{engine}] {finding.checklist_item_id:<9} 段{anchor} {finding.headline}")
    if report.notes:
        print("=== notes ===")
        for note in report.notes:
            print("  -", note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
