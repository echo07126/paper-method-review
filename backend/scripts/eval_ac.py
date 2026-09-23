"""AC-2/AC-3 评测：分组统计（规则夹具 fixtures 与真实论文 real 分开），按需求 9.1 口径。"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.engine.checklist import load_checklist  # noqa: E402
from app.engine.llm_provider import build_provider  # noqa: E402
from app.engine.reviewer import review_document  # noqa: E402
from app.parsers.registry import parse_document  # noqa: E402

SAMPLES = ROOT / "samples"
ANCHOR_TOLERANCE = 1


def sample_docx(truth: dict) -> Path:
    preferred = {"real": ["real"], "fixture": ["fixtures"]}.get(truth.get("type"), ["real", "fixtures"])
    for sub_dir in preferred:
        candidate = SAMPLES / sub_dir / f"{truth['sample_id']}.docx"
        if candidate.exists():
            return candidate
    return SAMPLES / "real" / f"{truth['sample_id']}.docx"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="启用模型判定（需联网与 Key）")
    args = parser.parse_args()

    items = load_checklist(ROOT / "checklists" / "quant-ai-v1.json")
    provider = build_provider(get_settings()) if args.llm else None

    rows = []
    groups = {
        name: {"expected": 0, "hit": 0, "fp": 0, "anchor_checked": 0, "anchor_ok": 0, "samples": 0}
        for name in ("fixture", "real", "review", "empirical", "planted")
    }

    for truth_path in sorted((SAMPLES / "ground_truth").glob("*.json")):
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        docx_path = sample_docx(truth)
        if not docx_path.exists() or "items" not in truth:
            continue
        document = parse_document(docx_path, docx_path.name, None)
        report = review_document(document, items, provider=provider, use_llm=args.llm)

        problems = {f.checklist_item_id: f for f in report.findings if f.verdict.value == "problem"}
        detected = set(problems)
        expected_items = {item["checklist_item_id"]: item for item in truth["items"]}
        expected = set(expected_items)
        hit = expected & detected
        false_positives = detected - expected

        anchor_checked = anchor_ok = 0
        for item_id in hit:
            finding = problems[item_id]
            expected_anchor = expected_items[item_id].get("anchor", {}).get("paragraph_index")
            if expected_anchor is None or not finding.anchors:
                continue
            anchor_checked += 1
            if abs(finding.anchors[0].paragraph_index - expected_anchor) <= ANCHOR_TOLERANCE:
                anchor_ok += 1

        group_name = truth.get("type") if truth.get("type") in groups else "fixture"
        group = groups[group_name]
        group["samples"] += 1
        group["expected"] += len(expected)
        group["hit"] += len(hit)
        group["fp"] += len(false_positives)
        group["anchor_checked"] += anchor_checked
        group["anchor_ok"] += anchor_ok

        rows.append((truth["sample_id"], group_name, len(expected), len(hit), sorted(expected - detected), sorted(false_positives)))

    print(f"模式：{'规则 + LLM（顾问模式）' if args.llm else '仅规则'}")
    print(f"{'样本':<16}{'分组':<10}{'期望':<6}{'命中':<6}漏报 / 误报")
    for sample_id, group_name, expected_count, hit_count, missed, false_positives in rows:
        print(f"{sample_id:<16}{group_name:<10}{expected_count:<6}{hit_count:<6}{missed} / {false_positives}")

    print()
    for group_name in ("fixture", "real", "review", "empirical", "planted"):
        group = groups[group_name]
        if group["samples"] == 0:
            continue
        label = {"fixture": "规则夹具 fixtures", "real": "真实论文 real", "review": "综述/理论论文 review（防误报）", "empirical": "规范实证论文 empirical（防误报）", "planted": "预埋缺陷实证 planted（阳性召回）"}[group_name]
        print(f"[{label}] {group['samples']} 篇 / {group['expected']} 条标准答案")
        if group["expected"] == 0:
            print(f"  仅检查误报：误报 {group['fp']} 条（期望 0 条问题）")
            continue
        rate = group["hit"] / group["expected"]
        precision = group["hit"] / (group["hit"] + group["fp"]) if (group["hit"] + group["fp"]) else 0
        anchor_rate = group["anchor_ok"] / group["anchor_checked"] if group["anchor_checked"] else 0
        print(f"  AC-2 检出率 = {group['hit']}/{group['expected']} = {rate:.0%}")
        print(f"  精确率 = {group['hit']}/{group['hit'] + group['fp']} = {precision:.0%}")
        print(f"  AC-3 定位准确率 = {group['anchor_ok']}/{group['anchor_checked']} = {anchor_rate:.0%}（容差 ±{ANCHOR_TOLERANCE} 段）")

    total_expected = sum(g["expected"] for g in groups.values())
    total_hit = sum(g["hit"] for g in groups.values())
    total_fp = sum(g["fp"] for g in groups.values())
    total_anchor_checked = sum(g["anchor_checked"] for g in groups.values())
    total_anchor_ok = sum(g["anchor_ok"] for g in groups.values())
    print()
    print(f"[合计] {total_hit}/{total_expected} = {(total_hit / total_expected if total_expected else 0):.0%} 检出，"
          f"精确率 {(total_hit / (total_hit + total_fp) if (total_hit + total_fp) else 0):.0%}，"
          f"定位 {(total_anchor_ok / total_anchor_checked if total_anchor_checked else 0):.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
