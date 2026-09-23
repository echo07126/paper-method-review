"""eval_ac：期望为 0 的分组只统计误报，不显示 0%。"""
from pathlib import Path

path = Path(__file__).resolve().parent / "eval_ac.py"
text = path.read_text(encoding="utf-8")
old = '''        rate = group["hit"] / group["expected"] if group["expected"] else 0
        precision = group["hit"] / (group["hit"] + group["fp"]) if (group["hit"] + group["fp"]) else 0
        anchor_rate = group["anchor_ok"] / group["anchor_checked"] if group["anchor_checked"] else 0
        label = {"fixture": "规则夹具 fixtures", "real": "真实论文 real", "review": "综述/理论论文 review（防误报）"}[group_name]
        print(f"[{label}] {group['samples']} 篇 / {group['expected']} 条标准答案")
        print(f"  AC-2 检出率 = {group['hit']}/{group['expected']} = {rate:.0%}")
        print(f"  精确率 = {group['hit']}/{group['hit'] + group['fp']} = {precision:.0%}")
        print(f"  AC-3 定位准确率 = {group['anchor_ok']}/{group['anchor_checked']} = {anchor_rate:.0%}（容差 ±{ANCHOR_TOLERANCE} 段）")'''
new = '''        label = {"fixture": "规则夹具 fixtures", "real": "真实论文 real", "review": "综述/理论论文 review（防误报）"}[group_name]
        print(f"[{label}] {group['samples']} 篇 / {group['expected']} 条标准答案")
        if group["expected"] == 0:
            print(f"  仅检查误报：误报 {group['fp']} 条（期望 0 条问题）")
            continue
        rate = group["hit"] / group["expected"]
        precision = group["hit"] / (group["hit"] + group["fp"]) if (group["hit"] + group["fp"]) else 0
        anchor_rate = group["anchor_ok"] / group["anchor_checked"] if group["anchor_checked"] else 0
        print(f"  AC-2 检出率 = {group['hit']}/{group['expected']} = {rate:.0%}")
        print(f"  精确率 = {group['hit']}/{group['hit'] + group['fp']} = {precision:.0%}")
        print(f"  AC-3 定位准确率 = {group['anchor_ok']}/{group['anchor_checked']} = {anchor_rate:.0%}（容差 ±{ANCHOR_TOLERANCE} 段）")'''
if old in text:
    path.write_text(text.replace(old, new), encoding="utf-8")
    print("零期望组显示已修正")
else:
    print("[warn] 未找到打印块")
