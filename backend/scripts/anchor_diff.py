"""列出每个样本的（条目, GT锚点, 系统锚点, 差值），定位 AC-3 失分点。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.engine.checklist import load_checklist  # noqa: E402
from app.engine.reviewer import review_document  # noqa: E402
from app.parsers.registry import parse_document  # noqa: E402

items = load_checklist(ROOT / "checklists" / "quant-ai-v1.json")
for truth_path in sorted((ROOT / "samples" / "ground_truth").glob("real-*.json")):
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    docx = ROOT / "samples" / "real" / f"{truth['sample_id']}.docx"
    if not docx.exists():
        continue
    document = parse_document(docx, docx.name, None)
    report = review_document(document, items)
    problems = {f.checklist_item_id: f for f in report.findings if f.verdict.value == "problem"}
    rows = []
    for item in truth["items"]:
        found = problems.get(item["checklist_item_id"])
        if not found:
            continue
        gt = item.get("anchor", {}).get("paragraph_index")
        got = found.anchors[0].paragraph_index if found.anchors else None
        if gt is not None and got is not None and abs(got - gt) > 1:
            rows.append(f"{item['checklist_item_id']}(GT={gt}, 系统={got})")
    if rows:
        print(f"{truth['sample_id']}: " + " | ".join(rows))
