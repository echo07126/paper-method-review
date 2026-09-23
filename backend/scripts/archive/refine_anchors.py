"""按章节语义精确锚点；并让 _last_body_anchor 排除“参考文献条目”式段落。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "backend" / "app" / "engine" / "rules.py"
text = path.read_text(encoding="utf-8")

# 1) _last_body_anchor 排除引用条目（形如 "[1] Author..."）
text = text.replace(
    '''    hits = [
        paragraph.index
        for paragraph in document.paragraphs
        if not paragraph.is_heading and paragraph.style != "Table" and compiled.search(paragraph.text)
    ]''',
    '''    hits = [
        paragraph.index
        for paragraph in document.paragraphs
        if not paragraph.is_heading
        and paragraph.style != "Table"
        and not re.match(r"^\\s*\\[\\d+\\]", paragraph.text)
        and compiled.search(paragraph.text)
    ]''',
)

# 2) R-04：首个“基线方法”正文段
text = text.replace(
    '        anchor_list = _last_body_anchor(document, r"(基线|对比方法|对照|baseline)") or anchors',
    '        anchor_list = _first_body_anchor(document, r"(基线方法|基线|对比方法|对照)") or anchors',
)
# 3) R-05：首个“模型结构/提出”正文段
text = text.replace(
    '    anchors = _first_body_anchor(document, r"(模块|机制|注意力)") or _anchor_for(elements, "novel_module")',
    '    anchors = _first_body_anchor(document, r"(本文提出|我们提出|改进的注意力|改进的模块|模型结构)") or _anchor_for(elements, "novel_module")',
)
# 4) R-06：首个“评价指标”正文段
text = text.replace(
    '        _first_body_anchor(document, r"(评价指标|评估指标|指标|度量)")',
    '        _first_body_anchor(document, r"(评价指标|评估指标|度量方式)")',
)
# 5) R-09：最后一个“统计检验”正文段
text = text.replace(
    '                     _last_body_anchor(document, r"(检验|显著性|p\\s*[<=>]|结果)") or anchors, "R-09")]',
    '                     _last_body_anchor(document, r"(统计检验|显著性|p\\s*[<>=])") or anchors, "R-09")]',
)
# 6) R-10：首个“主结果/表”正文段
text = text.replace(
    '                     _first_body_anchor(document, r"(主结果|结果|性能)") or anchors, "R-10")]',
    '                     _first_body_anchor(document, r"(表\\s*[12]|主结果)") or anchors, "R-10")]',
)
# 7) R-12：首个“超参数取值”正文段
text = text.replace(
    '                         _first_body_anchor(document, r"(超参数|学习率|批量大小|Dropout|权重衰减|卷积核)") or anchors, "R-12")]',
    '                         _first_body_anchor(document, r"(超参数|学习率|批量大小|Dropout率|权重衰减|卷积核数)") or anchors, "R-12")]',
)
# 8) R-14：首个“训练细节”正文段
text = text.replace(
    '    anchor_list = _first_body_anchor(document, r"(训练细节|优化器|学习率|批量大小|Dropout|权重衰减)") or anchors',
    '    anchor_list = _first_body_anchor(document, r"(训练细节|学习率|批量大小|Dropout|权重衰减)") or anchors',
)
# 9) R-15：首个“讨论/局限/结论”正文段
text = text.replace(
    '''    body_indexes = [p.index for p in document.paragraphs if p.style != "Table"]
    anchor_index = max(body_indexes) if body_indexes else _last_paragraph_index(document)
    return [_problem("R-15"''',
    '''    anchor_list = _first_body_anchor(document, r"(讨论|局限|结论)") or [
        _anchor(max([p.index for p in document.paragraphs if p.style != "Table"], default=0))
    ]
    return [_problem("R-15"''',
)
text = text.replace(
    '                     [_anchor(anchor_index)], "R-15")]',
    '                     anchor_list, "R-15")]',
)

path.write_text(text, encoding="utf-8")
print("锚点精确化完成")
