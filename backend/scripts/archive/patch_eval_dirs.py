"""eval_ac 支持 review 类型样本（优先 real，其次 fixtures）。"""
from pathlib import Path

path = Path(__file__).resolve().parent / "eval_ac.py"
text = path.read_text(encoding="utf-8")
old = '''def sample_docx(truth: dict) -> Path:
    sub_dir = "real" if truth.get("type") == "real" else "fixtures"
    return SAMPLES / sub_dir / f"{truth['sample_id']}.docx"'''
new = '''def sample_docx(truth: dict) -> Path:
    preferred = {"real": ["real"], "fixture": ["fixtures"]}.get(truth.get("type"), ["real", "fixtures"])
    for sub_dir in preferred:
        candidate = SAMPLES / sub_dir / f"{truth['sample_id']}.docx"
        if candidate.exists():
            return candidate
    return SAMPLES / "real" / f"{truth['sample_id']}.docx"'''
if old in text:
    path.write_text(text.replace(old, new), encoding="utf-8")
    print("eval_ac 已支持 review 类型样本")
else:
    print("[warn] 未找到 sample_docx 锚点")
