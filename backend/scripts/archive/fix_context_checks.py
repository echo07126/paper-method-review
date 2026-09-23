"""把 R-03 划分细节与 R-12 搜索范围改为“段落上下文”判定，避免被正文中的比值/方括号误触发。"""
from pathlib import Path

path = Path(__file__).resolve().parents[2] / "backend" / "app" / "engine" / "rules.py"
text = path.read_text(encoding="utf-8")

# R-03：只在“划分相关段落”里找比例/折数/种子
old03 = '''    if has_element(elements, "data_split"):
        if SPLIT_DETAIL_PATTERN.search(_document_text(document)):
            return [_pass("R-03", "已描述数据划分", "R-03", anchors)]'''
new03 = '''    if has_element(elements, "data_split"):
        split_paragraphs = [
            p.text
            for p in document.paragraphs
            if re.search(r"(划分|训练集|验证集|测试集|交叉验证)", p.text)
        ]
        if any(SPLIT_DETAIL_PATTERN.search(t) for t in split_paragraphs):
            return [_pass("R-03", "已描述数据划分", "R-03", anchors)]'''
if old03 in text:
    text = text.replace(old03, new03)
    print("R-03 已改为段落上下文判定")

# R-12：只在“超参数相关段落”里找搜索范围
old12 = '''    body_text = _document_text(document)
    if HYPER_SEARCH_SIGNAL.search(body_text) and HYPER_RANGE_PATTERN.search(body_text):
        return [_pass("R-12", "已说明超参数选择依据", "R-12", anchors)]'''
new12 = '''    hyper_paragraphs = [
        p.text
        for p in document.paragraphs
        if re.search(r"(超参数|学习率|批量大小|批大小|Dropout|权重衰减|卷积核|搜索|调参)", p.text)
    ]
    if HYPER_SEARCH_SIGNAL.search(_document_text(document)) and any(
        HYPER_RANGE_PATTERN.search(t) for t in hyper_paragraphs
    ):
        return [_pass("R-12", "已说明超参数选择依据", "R-12", anchors)]'''
if old12 in text:
    text = text.replace(old12, new12)
    print("R-12 已改为段落上下文判定")

path.write_text(text, encoding="utf-8")
