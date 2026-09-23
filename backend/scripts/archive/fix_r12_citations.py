"""R-12：匹配搜索范围前先剔除引用角标（避免把 训练[8] 的方括号当作取值范围）。"""
from pathlib import Path

path = Path(__file__).resolve().parents[2] / "backend" / "app" / "engine" / "rules.py"
text = path.read_text(encoding="utf-8")
old = '''    if HYPER_SEARCH_SIGNAL.search(_document_text(document)) and any(
        HYPER_RANGE_PATTERN.search(t) for t in hyper_paragraphs
    ):'''
new = '''    citation_stripped = [
        re.sub(r"\\[\\s*\\d[\\d\\s,，\\-–—]*\\]", "", t) for t in hyper_paragraphs
    ]
    if HYPER_SEARCH_SIGNAL.search(_document_text(document)) and any(
        HYPER_RANGE_PATTERN.search(t) for t in citation_stripped
    ):'''
if old in text:
    path.write_text(text.replace(old, new), encoding="utf-8")
    print("R-12 已剔除引用角标")
else:
    print("[warn] 未找到 R-12 锚点")
