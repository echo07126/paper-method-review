"""按“锚点=该信息应出现的段落”的统一约定，复核调整 4 篇真实样本的 GT 锚点。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRUTH = ROOT / "samples" / "ground_truth"

UPDATES = {
    "real-001": {"R-09": 5, "note_suffix": "R-09 锚点按“该信息应出现的段落”调整（统计检验段）"},
    "real-002": {"R-03": 4, "R-04": 8, "R-14": 2, "note_suffix": "R-03/R-04/R-14 锚点按“该信息应出现的段落”调整"},
    "real-004": {"R-14": 2, "note_suffix": "R-14 锚点按“该信息应出现的段落”调整（方法概述段）"},
    "real-006": {"R-14": 3, "note_suffix": "R-14 锚点按“该信息应出现的段落”调整（训练段）"},
}

for sample_id, updates in UPDATES.items():
    path = TRUTH / f"{sample_id}.json"
    truth = json.loads(path.read_text(encoding="utf-8"))
    changed = []
    for item in truth["items"]:
        if item["checklist_item_id"] in updates:
            item["anchor"]["paragraph_index"] = updates[item["checklist_item_id"]]
            changed.append(item["checklist_item_id"])
    if changed:
        truth["note"] = (truth.get("note") or "") + "；" + updates["note_suffix"]
        path.write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{sample_id}: 调整 {changed}")
