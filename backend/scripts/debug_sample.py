"""调试：打印样本的要素命中与规则判定，定位漏检/误报原因。"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.engine.elements import extract_elements  # noqa: E402
from app.engine.rules import run_rules  # noqa: E402
from app.parsers.registry import parse_document  # noqa: E402

targets = sys.argv[1:] or ["real-001", "real-002", "real-003", "real-004"]
for sample_id in targets:
    for sub in ("real", "fixtures"):
        path = ROOT / "samples" / sub / f"{sample_id}.docx"
        if not path.exists():
            continue
        document = parse_document(path, path.name, None)
        elements = extract_elements(document)
        counts = Counter(element.type for element in elements)
        print(f"=== {sample_id} 段落={len(document.paragraphs)} 要素={dict(counts)}")
        for finding in run_rules(document, elements):
            print(f"   [{finding.verdict.value}] {finding.checklist_item_id} {finding.headline}")
