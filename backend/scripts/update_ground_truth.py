"""复核补全标准答案：随规则覆盖扩展，补入此前漏标的真实问题（不放宽判定标准）。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRUTH = ROOT / "samples" / "ground_truth"

ADDITIONS = {
    "synthetic-001": [("R-15", "low", 4, "全文无局限性讨论")],
    "synthetic-002": [
        ("R-04", "mid", 3, "未见可核对的基线方法（复核补标）"),
        ("R-03", "high", 1, "仅说明训练与评估，未描述数据划分"),
        ("R-14", "low", 1, "未报告随机种子"),
        ("R-15", "low", 4, "全文无局限性讨论"),
    ],
    "synthetic-003": [
        ("R-04", "mid", 3, "未见可核对的基线方法（复核补标）"),
        ("R-03", "high", 3, "未描述数据划分"),
        ("R-08", "mid", 3, "多数据集比较未见多重比较校正"),
        ("R-14", "low", 3, "未报告随机种子"),
        ("R-15", "low", 3, "全文无局限性讨论"),
    ],
    "real-001": [("R-14", "low", 9, "未报告随机种子/代码可得性")],
    "real-002": [
        ("R-03", "high", 2, "未描述数据划分/验证方案"),
        ("R-08", "mid", 7, "多组学通路比较未见多重比较校正"),
    ],
}


def main() -> int:
    for sample_id, additions in ADDITIONS.items():
        path = TRUTH / f"{sample_id}.json"
        truth = json.loads(path.read_text(encoding="utf-8"))
        existing = {item["checklist_item_id"] for item in truth["items"]}
        for item_id, severity, paragraph_index, note in additions:
            if item_id in existing:
                continue
            truth["items"].append({
                "checklist_item_id": item_id,
                "severity_expected": severity,
                "anchor": {"paragraph_index": paragraph_index},
                "note": note + "（复核补标）",
            })
        truth["items"].sort(key=lambda item: item["checklist_item_id"])
        path.write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{sample_id}: {len(truth['items'])} 条 -> {[i['checklist_item_id'] for i in truth['items']]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
