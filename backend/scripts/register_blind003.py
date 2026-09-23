"""登记盲测论文3（规范实证论文，期望 0 问题）并新增 empirical 分组。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import shutil

src = ROOT / "samples" / "real" / "raw" / "盲测论文3.docx"
dst = ROOT / "samples" / "real" / "blind-003.docx"
shutil.copyfile(src, dst)

truth = ROOT / "samples" / "ground_truth" / "blind-003.json"
truth.write_text(json.dumps({
    "sample_id": "blind-003",
    "title": "多尺度卷积与类别加权损失的中文短文本分类：基准实验与统计检验（规范实证）",
    "type": "empirical",
    "source": "用户提供（盲测）",
    "license": "user-provided",
    "language": "zh",
    "items": [],
    "note": "规范良好的实证论文盲测：期望 0 问题（检验误报）；详见 docs/evaluation/blind-tests/blind-003-中文短文本分类.md",
}, ensure_ascii=False, indent=2), encoding="utf-8")

path = ROOT / "backend" / "scripts" / "eval_ac.py"
text = path.read_text(encoding="utf-8")
text = text.replace(
    'for name in ("fixture", "real", "review")',
    'for name in ("fixture", "real", "review", "empirical")',
)
text = text.replace(
    '    for group_name in ("fixture", "real", "review"):',
    '    for group_name in ("fixture", "real", "review", "empirical"):',
)
text = text.replace(
    '        label = {"fixture": "规则夹具 fixtures", "real": "真实论文 real", "review": "综述/理论论文 review（防误报）"}[group_name]',
    '        label = {"fixture": "规则夹具 fixtures", "real": "真实论文 real", "review": "综述/理论论文 review（防误报）", "empirical": "规范实证论文 empirical（防误报）"}[group_name]',
)
path.write_text(text, encoding="utf-8")
print("blind-003 已登记，empirical 分组已加入")
