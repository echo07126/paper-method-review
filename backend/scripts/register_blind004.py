"""登记盲测论文4（预埋缺陷实证论文，16 条预埋/本方覆盖 14 条）并新增 planted 分组。"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
shutil.copyfile(ROOT / "samples" / "real" / "raw" / "盲测论文4.docx", ROOT / "samples" / "real" / "blind-004.docx")

ITEMS = [
    ("R-02", "low", 11, "三个数据集均未给出样本量依据/功效分析"),
    ("R-03", "high", 27, "4.1 未给出划分比例与随机种子"),
    ("R-04", "mid", 29, "仅以 BERT 作为单一基线"),
    ("R-05", "mid", 14, "提出“改进的注意力模块”，全文无消融实验"),
    ("R-06", "mid", 24, "只报告参数量/时间/耗时等工程指标，无分类性能指标"),
    ("R-07", "high", 39, "报告 p<0.05 但未说明检验方法"),
    ("R-08", "mid", 37, "3 数据集×4 模型比较未见多重比较校正"),
    ("R-09", "mid", 39, "未报告置信区间/效应量"),
    ("R-10", "mid", 31, "未报告重复次数与方差"),
    ("R-11", "low", 43, "结论“普遍适用，可推广至各类文本分类任务”"),
    ("R-12", "mid", 21, "只列超参数取值，无搜索范围/依据"),
    ("R-14", "low", 21, "未报告随机种子与代码可得性"),
    ("R-15", "low", 41, "讨论/结论均无局限性"),
    ("R-REF-01", "low", 8, "正文引用 [99]，参考文献表无此条"),
]
truth = {
    "sample_id": "blind-004",
    "title": "基于多尺度卷积与改进注意力机制的中文短文本分类方法（预埋缺陷实证）",
    "type": "planted",
    "source": "用户提供（盲测）",
    "license": "user-provided",
    "language": "zh",
    "items": [
        {"checklist_item_id": i, "severity_expected": s, "anchor": {"paragraph_index": p}, "note": n}
        for i, s, p, n in ITEMS
    ],
    "note": "预埋缺陷论文（生成方自检 16/16 落位）；本清单为人工核对后可判定的 14 条；详见 docs/evaluation/blind-tests/blind-004-预埋缺陷实证论文.md",
}
path = ROOT / "samples" / "ground_truth" / "blind-004.json"
path.write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")

eval_path = ROOT / "backend" / "scripts" / "eval_ac.py"
text = eval_path.read_text(encoding="utf-8")
text = text.replace('for name in ("fixture", "real", "review", "empirical")', 'for name in ("fixture", "real", "review", "empirical", "planted")')
text = text.replace('    for group_name in ("fixture", "real", "review", "empirical"):', '    for group_name in ("fixture", "real", "review", "empirical", "planted"):')
text = text.replace(
    '"empirical": "规范实证论文 empirical（防误报）"}[group_name]',
    '"empirical": "规范实证论文 empirical（防误报）", "planted": "预埋缺陷实证 planted（阳性召回）"}[group_name]',
)
eval_path.write_text(text, encoding="utf-8")
print("blind-004 已登记，planted 分组已加入")
