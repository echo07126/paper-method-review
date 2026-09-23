"""校准论文类型识别阈值：打印盲测论文与全部样本的分类结果。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.engine.paper_type import classify  # noqa: E402
from app.parsers.registry import parse_document  # noqa: E402

targets = [("盲测论文", ROOT / "samples" / "real" / "raw" / "盲测论文.docx")]
for sub in ("real", "fixtures"):
    targets += [(p.stem, p) for p in sorted((ROOT / "samples" / sub).glob("*.docx"))]

for name, path in targets:
    document = parse_document(path, path.name, None)
    kind, evidence = classify(document)
    print(f"{name:<16} -> {kind:<10} {evidence}")
