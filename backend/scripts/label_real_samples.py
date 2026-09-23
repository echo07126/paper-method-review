"""为 real 样本写入人工核对后的标准答案（依据改写正文逐条判定）。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRUTH = ROOT / "samples" / "ground_truth"

LABELS = {
    "real-001": [
        {"checklist_item_id": "R-02", "severity_expected": "low", "anchor": {"paragraph_index": 2}, "note": "仅 14 名受试者，未见样本量依据/功效分析"},
        {"checklist_item_id": "R-08", "severity_expected": "mid", "anchor": {"paragraph_index": 9}, "note": "多模型比较未做多重比较校正"},
        {"checklist_item_id": "R-09", "severity_expected": "mid", "anchor": {"paragraph_index": 9}, "note": "报告分类性能但未见置信区间/效应量"},
        {"checklist_item_id": "R-15", "severity_expected": "low", "anchor": {"paragraph_index": 9}, "note": "未见局限性讨论"},
    ],
"real-003": [
        {"checklist_item_id": "R-02", "severity_expected": "low", "anchor": {"paragraph_index": 3}, "note": "10,015 张图像但未见样本量依据"},
        {"checklist_item_id": "R-07", "severity_expected": "high", "anchor": {"paragraph_index": 3}, "note": "报告 p 值但未说明检验方法"},
        {"checklist_item_id": "R-09", "severity_expected": "mid", "anchor": {"paragraph_index": 3}, "note": "报告性能但未见置信区间"},
    ],
    "real-004": [
        {"checklist_item_id": "R-02", "severity_expected": "low", "anchor": {"paragraph_index": 2}, "note": "312 例但未见样本量依据"},
        {"checklist_item_id": "R-04", "severity_expected": "mid", "anchor": {"paragraph_index": 7}, "note": "未见基线模型对比"},
        {"checklist_item_id": "R-14", "severity_expected": "low", "anchor": {"paragraph_index": 8}, "note": "未报告随机种子/代码可得性"},
    ],
    "real-002": [
        {"checklist_item_id": "R-02", "severity_expected": "low", "anchor": {"paragraph_index": 2}, "note": "多中心队列但未见样本量依据/功效分析"},
        {"checklist_item_id": "R-04", "severity_expected": "mid", "anchor": {"paragraph_index": 4}, "note": "仅单一 MV3S 架构，缺少基线模型对比"},
        {"checklist_item_id": "R-09", "severity_expected": "mid", "anchor": {"paragraph_index": 4}, "note": "AUC 未给置信区间"},
        {"checklist_item_id": "R-14", "severity_expected": "low", "anchor": {"paragraph_index": 4}, "note": "未报告随机种子/代码与数据可得性"},
        {"checklist_item_id": "R-15", "severity_expected": "low", "anchor": {"paragraph_index": 8}, "note": "未见局限性讨论"},
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
