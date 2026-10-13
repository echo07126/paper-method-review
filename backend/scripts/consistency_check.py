"""多轮一致性测试：同一论文连续审查 N 轮，量化条目覆盖与判定稳定性。

⚠ 本脚本会**真实调用模型 API**（默认 3 轮完整审查，按量计费），因此不属于离线门禁，
需要显式传 `--confirm-billing` 才会执行；CI 与「随手跑一套检查」时请跳过它。
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.engine.checklist import load_checklist  # noqa: E402
from app.engine.llm_provider import build_provider  # noqa: E402
from app.engine.reviewer import review_document  # noqa: E402
from app.models.schemas import DocumentIR, Paragraph, Section  # noqa: E402

TEXT = [
    "本研究纳入 1,240 例眼底彩照，按 8:2 划分为训练集与验证集。",
    "超参数在验证集上通过网格搜索确定，最终在测试集上评估。",
    "结果显示准确率为 0.912，较基线提升 2.1 个百分点（p<0.05）。",
    "本文提出了一种改进的注意力机制模块，可推广至各类医疗影像场景。",
]

DEFAULT_ROUNDS = 3


def build_document() -> DocumentIR:
    paragraphs = [Paragraph(index=i, text=text) for i, text in enumerate(TEXT)]
    return DocumentIR(
        source_name="consistency_demo.docx",
        parser="synthetic",
        parser_version="0",
        sections=[Section(id="sec_1", title="2. 方法", level=1, paragraph_index=0)],
        paragraphs=paragraphs,
    )


def verdict_map(report) -> dict[str, str]:
    return {finding.checklist_item_id: finding.verdict.value for finding in report.findings}


def problem_set(report) -> set[str]:
    return {f.checklist_item_id for f in report.findings if f.verdict.value == "problem"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS, help=f"审查轮数（默认 {DEFAULT_ROUNDS}）")
    parser.add_argument(
        "--confirm-billing",
        action="store_true",
        help="确认本脚本会真实调用模型 API 并按量计费；不传则直接退出，避免误触发付费调用",
    )
    args = parser.parse_args()

    if not args.confirm_billing:
        print("SKIP: 本脚本会真实调用模型 API（按量计费），需显式传 --confirm-billing 才会执行。")
        return 0
    if args.rounds < 2:
        print("FAIL: 一致性对比至少需要 2 轮（--rounds >= 2）。")
        return 2

    settings = get_settings()
    provider = build_provider(settings)
    if provider is None:
        print("FAIL: 未配置模型服务")
        return 2

    items = load_checklist(ROOT / "checklists" / "quant-ai-v1.json")
    reports = [
        review_document(build_document(), items, provider=provider, use_llm=True)
        for _ in range(args.rounds)
    ]

    print("model:", settings.deepseek_model, " rounds:", args.rounds)
    for index, report in enumerate(reports, start=1):
        print(f"  round{index}: problems={report.counts['total']} assessed={report.counts['assessed']} "
              f"llm_tokens_out={report.tokens.get('output', 0)} duration_ms={report.duration_ms}")

    maps = [verdict_map(report) for report in reports]
    common_items = set.intersection(*(set(m) for m in maps)) if maps else set()
    stable = sum(1 for item in common_items if len({m[item] for m in maps}) == 1)
    print(f"条目覆盖：每轮判定条目数 = {[len(m) for m in maps]}，{args.rounds} 轮共有条目 = {len(common_items)}")
    if common_items:
        print(f"判定稳定率（{args.rounds} 轮一致）= {stable}/{len(common_items)} = {stable / len(common_items):.0%}")

    pset = [problem_set(report) for report in reports]
    inter = set.intersection(*pset) if pset else set()
    union = set.union(*pset) if pset else set()
    print(f"问题集合：每轮 problem 条目数 = {[len(s) for s in pset]}，{args.rounds} 轮交集 = {len(inter)}")
    print(f"问题集合 Jaccard（{args.rounds} 轮并集为分母）= {len(inter) / len(union) if union else 0:.0%}")

    for index, report in enumerate(reports, start=1):
        counter = Counter(f.severity.value for f in report.findings if f.verdict.value == "problem")
        print(f"  round{index} 严重级分布：{dict(counter)}")
    print("CONSISTENCY CHECK DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
