"""章节锚点修复：子标题不中断；R-03/R-04 优先匹配专属小节。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "backend" / "app" / "engine" / "rules.py"
text = path.read_text(encoding="utf-8")

# 1) 子标题不中断搜索（只有“一级标题且不匹配”才结束）
old = '''    inside = False
    for paragraph in document.paragraphs:
        if paragraph.is_heading:
            if section_re.search(paragraph.text):
                inside = True
            elif inside:
                inside = False
            continue'''
new = '''    def _heading_level(paragraph) -> int:
        style = paragraph.style or ""
        parts = style.split()
        if len(parts) == 2 and parts[0] == "Heading" and parts[1].isdigit():
            return int(parts[1])
        return 0

    inside = False
    for paragraph in document.paragraphs:
        if paragraph.is_heading:
            if section_re.search(paragraph.text):
                inside = True
            elif inside and _heading_level(paragraph) <= 1:
                inside = False
            continue'''
if old in text:
    text = text.replace(old, new)
    print("章节锚点：子标题不再中断")
else:
    print("[warn] 未找到 inside 逻辑")

# 2) R-03：优先“数据划分”小节
text = text.replace(
    '_section_body_anchor(document, r"(数据划分|数据|实验|方法)", r"(划分|训练集|验证集|测试集|交叉验证)")',
    '(_section_body_anchor(document, r"(数据划分|数据划分与验证)", r"(划分|训练集|验证集|测试集|交叉验证)")\n'
    '         or _section_body_anchor(document, r"(数据|实验|方法)", r"(划分|训练集|验证集|测试集|交叉验证)"))',
)
# 3) R-04：优先“基线方法”小节
text = text.replace(
    '_section_body_anchor(document, r"(基线|对比|方法)", r"(基线|对比方法|对照)")',
    '(_section_body_anchor(document, r"(基线方法|基线|对比方法)", r"(基线|对比方法|对照|baseline)")\n'
    '         or _first_body_anchor(document, r"(基线|对比方法|对照)"))',
)
path.write_text(text, encoding="utf-8")
print("R-03/R-04 小节优先已应用")
