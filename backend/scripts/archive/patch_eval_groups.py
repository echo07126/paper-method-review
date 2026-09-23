"""eval_ac 分组：fixture / real / review 三组分别统计。"""
from pathlib import Path

path = Path(__file__).resolve().parent / "eval_ac.py"
text = path.read_text(encoding="utf-8")
text = text.replace(
    '''    groups = {
        "fixture": {"expected": 0, "hit": 0, "fp": 0, "anchor_checked": 0, "anchor_ok": 0, "samples": 0},
        "real": {"expected": 0, "hit": 0, "fp": 0, "anchor_checked": 0, "anchor_ok": 0, "samples": 0},
    }''',
    '''    groups = {
        name: {"expected": 0, "hit": 0, "fp": 0, "anchor_checked": 0, "anchor_ok": 0, "samples": 0}
        for name in ("fixture", "real", "review")
    }''',
)
text = text.replace(
    '        group_name = "real" if truth.get("type") == "real" else "fixture"',
    '        group_name = truth.get("type") if truth.get("type") in groups else "fixture"',
)
text = text.replace(
    '    for group_name in ("fixture", "real"):',
    '    for group_name in ("fixture", "real", "review"):',
)
text = text.replace(
    '        label = "规则夹具 fixtures" if group_name == "fixture" else "真实论文 real"',
    '        label = {"fixture": "规则夹具 fixtures", "real": "真实论文 real", "review": "综述/理论论文 review（防误报）"}[group_name]',
)
path.write_text(text, encoding="utf-8")
print("eval_ac 分组已改为三组")
