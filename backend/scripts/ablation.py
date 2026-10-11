"""消融实验：在固定评测集上对比「要素提取」与「证据门控」两个开关的组合影响。

五个配置（E/A/B/C/D，2×2 组合 + 全量）：

| 配置 | 要素提取 | 门控 | 模型 |
| --- | --- | --- | --- |
| E 基线 | 关 | 关 | 关 |
| A 仅要素 | 开 | 关 | 关 |
| B 仅门控 | 关 | 开 | 关 |
| C 规则全量 | 开 | 开 | 关 |
| D 高级应用 | 开 | 开 | **开**（需 `--llm`） |

- **要素提取关**：`reviewer.extract_elements` 返回空列表——规则不再有证据要素可用；
- **门控关**：跳过 `_attach_evidence`（证据门）/ `_apply_judge_tiers`（判定主体档）/ `_mark_unassessed`（未能判定）——无锚点结论不再降级、也不再产出「本项未能判定」；
- 生产代码不为评测加开关，本脚本用 `unittest.mock` 在进程内临时替换，退出即还原。

指标：检出率 / 精确率（= 1 − 误报率）/ 审查率（`quality.review_rate`）/ 平均 token / 平均耗时；若存在
`samples/ground_truth/elements/<sample_id>.json` 要素级标注，另测当前抽取器的要素 P/R/F1。

`--strict` 按 `THRESHOLDS` 回归下限校验，未达标返回非零（CI 门禁用）；不加该参数时只打印、恒返回 0。
"""
import argparse
import json
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import app.engine.reviewer as reviewer  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.engine.checklist import load_checklist  # noqa: E402
from app.engine.elements import extract_elements  # noqa: E402
from app.engine.llm_provider import build_provider  # noqa: E402
from app.engine.reviewer import review_document  # noqa: E402
from app.parsers.registry import parse_document  # noqa: E402

SAMPLES = ROOT / "samples"
ELEMENT_TRUTH_DIR = SAMPLES / "ground_truth" / "elements"

VARIANTS: list[tuple[str, dict[str, bool]]] = [
    ("E 基线", {"elements": False, "gates": False, "llm": False}),
    ("A 仅要素", {"elements": True, "gates": False, "llm": False}),
    ("B 仅门控", {"elements": False, "gates": True, "llm": False}),
    ("C 规则全量", {"elements": True, "gates": True, "llm": False}),
    ("D 高级应用", {"elements": True, "gates": True, "llm": True}),
]

# 回归下限（`--strict` 启用）：取值略低于当前实测，留出容差；未达标即判定退化并返回非零。
THRESHOLDS: dict[str, float] = {
    "C 规则全量 检出率": 0.95,
    "C 规则全量 精确率": 0.95,
    "要素抽取 F1": 0.85,
}


def sample_docx(truth: dict) -> Path:
    preferred = {"real": ["real"], "fixture": ["fixtures"]}.get(truth.get("type"), ["real", "fixtures"])
    for sub_dir in preferred:
        candidate = SAMPLES / sub_dir / f"{truth['sample_id']}.docx"
        if candidate.exists():
            return candidate
    return SAMPLES / "real" / f"{truth['sample_id']}.docx"


def _patch_stack(flags: dict[str, bool]) -> list:
    patches = []
    if not flags["elements"]:
        patches.append(mock.patch.object(reviewer, "extract_elements", lambda document: []))
    if not flags["gates"]:
        patches.append(
            mock.patch.object(reviewer, "_attach_evidence", lambda merged, items, elements, rule_anchors: merged)
        )
        patches.append(
            mock.patch.object(reviewer, "_apply_judge_tiers", lambda findings, items, force_advisory: findings)
        )
        patches.append(mock.patch.object(reviewer, "_mark_unassessed", lambda findings, items: findings))
    return patches


def _load_cases() -> list[tuple[dict, Path]]:
    cases: list[tuple[dict, Path]] = []
    for truth_path in sorted((SAMPLES / "ground_truth").glob("*.json")):
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        docx_path = sample_docx(truth)
        if docx_path.exists() and "items" in truth:
            cases.append((truth, docx_path))
    return cases


def run_variant(name: str, flags: dict[str, bool], cases: list, items: list, checklist_ids: set[str], num_llm: int) -> dict:
    provider = build_provider(get_settings()) if flags["llm"] else None
    use_llm = bool(flags["llm"] and provider is not None)
    expected_total = hit_total = fp_total = 0
    review_rates: list[float] = []
    tokens_total = duration_total = 0
    for truth, docx_path in cases:
        document = parse_document(docx_path, docx_path.name, None)
        patches = _patch_stack(flags)
        for patch in patches:
            patch.start()
        try:
            report = review_document(document, items, provider=provider, use_llm=use_llm)
        finally:
            for patch in reversed(patches):
                patch.stop()
        detected = {
            f.checklist_item_id
            for f in report.findings
            if f.verdict.value == "problem" and f.checklist_item_id in checklist_ids
        }
        expected = {item["checklist_item_id"] for item in truth["items"]}
        expected_total += len(expected)
        hit_total += len(expected & detected)
        fp_total += len(detected - expected)
        review_rates.append(report.quality.get("review_rate", 0.0))
        tokens_total += report.tokens.get("input", 0) + report.tokens.get("output", 0)
        duration_total += report.duration_ms
    count = len(cases)
    return {
        "variant": name,
        "detection": hit_total / expected_total if expected_total else 0.0,
        "precision": hit_total / (hit_total + fp_total) if (hit_total + fp_total) else 0.0,
        "fp_rate": fp_total / (hit_total + fp_total) if (hit_total + fp_total) else 0.0,
        "review_rate": sum(review_rates) / count if count else 0.0,
        "tokens": tokens_total / count if count else 0.0,
        "duration_ms": duration_total / count if count else 0.0,
        "llm": num_llm,
    }


def element_metrics(cases: list) -> dict | None:
    """按「文档 × 要素类型」测当前抽取器的 P/R/F1（需标注文件）。"""
    if not ELEMENT_TRUTH_DIR.exists():
        return None
    tp = predicted = annotated = 0
    covered = 0
    for truth, docx_path in cases:
        annotation_path = ELEMENT_TRUTH_DIR / f"{truth['sample_id']}.json"
        if not annotation_path.exists():
            continue
        gold = set(json.loads(annotation_path.read_text(encoding="utf-8")).get("elements", []))
        document = parse_document(docx_path, docx_path.name, None)
        predicted_types = {element.type for element in extract_elements(document)}
        tp += len(gold & predicted_types)
        predicted += len(predicted_types)
        annotated += len(gold)
        covered += 1
    if not covered:
        return None
    precision = tp / predicted if predicted else 0.0
    recall = tp / annotated if annotated else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"covered": covered, "precision": precision, "recall": recall, "f1": f1}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="额外跑 D 配置（需联网与 Key）")
    parser.add_argument("--strict", action="store_true", help="按回归下限校验，未达标返回非零（CI 用）")
    args = parser.parse_args()

    items = load_checklist(ROOT / "checklists" / "quant-ai-v1.json")
    checklist_ids = {item.id for item in items}
    cases = _load_cases()

    print(f"评测样本 {len(cases)} 篇 / 清单 {len(items)} 条")
    print()
    print(f"{'配置':<12}{'检出率':<10}{'精确率':<10}{'误报率':<10}{'审查率':<10}{'token/篇':<10}{'耗时ms/篇'}")
    measured: dict[str, float] = {}
    for name, flags in VARIANTS:
        if flags["llm"] and not args.llm:
            continue
        row = run_variant(name, flags, cases, items, checklist_ids, int(flags["llm"]))
        measured[f"{name} 检出率"] = row["detection"]
        measured[f"{name} 精确率"] = row["precision"]
        print(
            f"{name:<12}{row['detection']:<10.0%}{row['precision']:<10.0%}{row['fp_rate']:<10.0%}"
            f"{row['review_rate']:<10.0%}{row['tokens']:<10.0f}{row['duration_ms']:<10.0f}"
        )

    metrics = element_metrics(cases)
    print()
    if metrics:
        measured["要素抽取 F1"] = metrics["f1"]
        print(
            f"[要素抽取] 覆盖 {metrics['covered']} 篇标注：精确率 {metrics['precision']:.0%}、"
            f"召回率 {metrics['recall']:.0%}、F1 {metrics['f1']:.0%}（文档 × 要素类型口径）"
        )
    else:
        print("[要素抽取] 未找到 samples/ground_truth/elements/ 标注，跳过要素 P/R/F1。")

    if args.strict:
        failures = [
            f"{key} {measured.get(key, 0.0):.0%} < 下限 {floor:.0%}"
            for key, floor in THRESHOLDS.items()
            if measured.get(key, 0.0) < floor
        ]
        if failures:
            print("\n[门禁未通过] " + "；".join(failures))
            return 1
        print("\n[门禁通过] 要素抽取与规则口径均未低于回归下限。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())