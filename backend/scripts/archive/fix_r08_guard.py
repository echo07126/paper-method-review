"""R-08 加 AI 适用性守卫；synthetic-001 补标 R-12（复核确认为真实缺失）。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
rules = ROOT / "backend" / "app" / "engine" / "rules.py"
text = rules.read_text(encoding="utf-8")
old = '''def rule_multiple_comparison(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    if not MULTI_COMPARISON_SIGNAL.search(_document_text(document)):'''
new = '''def rule_multiple_comparison(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    if not _ai_empirical(document, elements):
        return []
    if not MULTI_COMPARISON_SIGNAL.search(_document_text(document)):'''
if old in text:
    rules.write_text(text.replace(old, new), encoding="utf-8")
    print("R-08 已加 AI 适用性守卫")
else:
    print("[warn] 未找到 R-08 锚点")

truth_path = ROOT / "samples" / "ground_truth" / "synthetic-001.json"
truth = json.loads(truth_path.read_text(encoding="utf-8"))
if "R-12" not in {i["checklist_item_id"] for i in truth["items"]}:
    truth["items"].append({"checklist_item_id": "R-12", "severity_expected": "mid",
                           "anchor": {"paragraph_index": 2}, "note": "仅说明网格搜索，未给出搜索范围（复核补标）"})
    truth["items"].sort(key=lambda i: i["checklist_item_id"])
    truth_path.write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
    print("synthetic-001 已补标 R-12")
