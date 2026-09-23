"""为 real-005/006/007 写入人工核对后的标准答案。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRUTH = ROOT / "samples" / "ground_truth"

LABELS = {
    "real-005": [
        {"checklist_item_id": "R-15", "severity_expected": "low", "anchor": {"paragraph_index": 8}, "note": "缺少局限讨论（非 AI 实证场景，模型类条目不适用）"},
    ],
    "real-006": [
        {"checklist_item_id": "R-02", "severity_expected": "low", "anchor": {"paragraph_index": 3}, "note": "54 个数据集但未见样本量依据"},
        {"checklist_item_id": "R-05", "severity_expected": "mid", "anchor": {"paragraph_index": 2}, "note": "提出 EXPP-Net 但未见消融实验"},
        {"checklist_item_id": "R-09", "severity_expected": "mid", "anchor": {"paragraph_index": 4}, "note": "报告 RMSE/SSIM 但未见置信区间"},
        {"checklist_item_id": "R-14", "severity_expected": "low", "anchor": {"paragraph_index": 8}, "note": "未报告随机种子/代码可得性"},
        {"checklist_item_id": "R-15", "severity_expected": "low", "anchor": {"paragraph_index": 9}, "note": "缺少局限讨论"},
    ],
    "real-007": [
        {"checklist_item_id": "R-02", "severity_expected": "low", "anchor": {"paragraph_index": 2}, "note": "591 份有效问卷但未见样本量依据"},
        {"checklist_item_id": "R-09", "severity_expected": "mid", "anchor": {"paragraph_index": 7}, "note": "报告显著性但未见置信区间"},
    ],
}


def main() -> int:
    for sample_id, items in LABELS.items():
        path = TRUTH / f"{sample_id}.json"
        if not path.exists():
            print(f"skip {sample_id}（标准答案文件不存在）")
            continue
        truth = json.loads(path.read_text(encoding="utf-8"))
        truth["items"] = items
        truth["note"] = "改写自 Europe PMC 开放获取全文（CC-BY）；标准答案由人工逐条核对标注"
        path.write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"labeled {sample_id}: {[i['checklist_item_id'] for i in items]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
