"""优化规则锚点：优先指向“缺陷应出现/出现”的正文段落（排除标题、摘要与表格行）。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "backend" / "app" / "engine" / "rules.py"
text = path.read_text(encoding="utf-8")

# 通用辅助：按模式找**首个**非标题、非表格正文段（可跳过摘要等前 N 段）
helper = '''
def _first_body_anchor(document: DocumentIR, pattern: str, skip_first: int = 3):
    compiled = re.compile(pattern)
    for paragraph in document.paragraphs:
        if paragraph.is_heading or paragraph.style == "Table" or paragraph.index < skip_first:
            continue
        if compiled.search(paragraph.text):
            return [_anchor(paragraph.index)]
    return []


def _last_body_anchor(document: DocumentIR, pattern: str):
    compiled = re.compile(pattern)
    hits = [
        paragraph.index
        for paragraph in document.paragraphs
        if not paragraph.is_heading and paragraph.style != "Table" and compiled.search(paragraph.text)
    ]
    return [_anchor(hits[-1])] if hits else []


def _anchor_for(elements: list[Element], *types: str) -> list[Anchor]:'''
text = text.replace("\ndef _anchor_for(elements: list[Element], *types: str) -> list[Anchor]:", helper, 1)

# R-03：指向“数据划分”段落
text = text.replace(
    '''    model_index = _paragraph_matching(document, re.compile(r"(训练|模型|评估|验证)"), last=True)
    anchor_list = [_anchor(model_index)] if model_index is not None else anchors
    return [_problem("R-03"''',
    '''    anchor_list = _last_body_anchor(document, r"(划分|训练集|验证集|测试集|交叉验证)") or anchors
    return [_problem("R-03"''',
)
text = text.replace(
    '''        return [_problem("R-03", Severity.HIGH, "未描述具体数据划分比例与随机种子",
                         "文中提到训练/验证/测试集，但未给出划分比例（或折数）与随机种子。",
                         "补充划分比例（如 8:1:1）或交叉验证折数，并写明随机种子以保障可复现。",
                         anchors, "R-03")]''',
    '''        return [_problem("R-03", Severity.HIGH, "未描述具体数据划分比例与随机种子",
                         "文中提到训练/验证/测试集，但未给出划分比例（或折数）与随机种子。",
                         "补充划分比例（如 8:1:1）或交叉验证折数，并写明随机种子以保障可复现。",
                         _last_body_anchor(document, r"(划分|训练集|验证集|测试集|交叉验证)") or anchors, "R-03")]''',
)

# R-04：单一基线 → 指向“基线方法”段落
text = text.replace(
    '''    if SINGLE_BASELINE_PATTERN.search(body_text):
        model_index = _paragraph_matching(document, re.compile(r"(模型|方法|基线)"), last=True)
        anchor_list = [_anchor(model_index)] if model_index is not None else anchors''',
    '''    if SINGLE_BASELINE_PATTERN.search(body_text):
        anchor_list = _last_body_anchor(document, r"(基线|对比方法|对照|baseline)") or anchors''',
)

# R-05：消融缺失 → 指向“模型结构”段落（首个含模块/机制的正文段）
text = text.replace(
    '''    anchors = _anchor_for(elements, "novel_module")
    if has_element(elements, "ablation"):''',
    '''    anchors = _first_body_anchor(document, r"(模块|机制|注意力)") or _anchor_for(elements, "novel_module")
    if has_element(elements, "ablation"):''',
)

# R-06：指标缺失 → 指向“评价指标”段落
text = text.replace(
    '''    anchors = _anchor_for(elements, "novel_module")
    body_text = _document_text(document)''',
    '''    anchors = (
        _first_body_anchor(document, r"(评价指标|评估指标|指标|度量)")
        or _first_body_anchor(document, r"(模块|机制|注意力)")
        or _anchor_for(elements, "novel_module")
    )
    body_text = _document_text(document)''',
)

# R-07 / R-09 / R-10 / R-12 / R-14：锚点指向对应正文段
text = text.replace(
    '''    return [_problem("R-07", Severity.HIGH, "报告了 p 值但未说明统计检验方法",
                     "文中出现 p 值表述，但未检出具体的统计检验描述。",
                     "补充所用检验方法、检验对象与自由度，并说明前提假设是否满足。",
                     _anchor_for(elements, "p_value"), "R-07")]''',
    '''    return [_problem("R-07", Severity.HIGH, "报告了 p 值但未说明统计检验方法",
                     "文中出现 p 值表述，但未检出具体的统计检验描述。",
                     "补充所用检验方法、检验对象与自由度，并说明前提假设是否满足。",
                     _last_body_anchor(document, r"(p\\s*[<=>]\\s*0?\\.\\d+|检验|显著性)") or _anchor_for(elements, "p_value"), "R-07")]''',
)
text = text.replace(
    '''    return [_problem("R-09", Severity.MID, "缺少效应量或置信区间",
                     "报告了性能指标或显著性检验，但未检出效应量或 95% 置信区间。",
                     "补充效应量与置信区间，避免只依据点估计或 p 值下结论。", anchors, "R-09")]''',
    '''    return [_problem("R-09", Severity.MID, "缺少效应量或置信区间",
                     "报告了性能指标或显著性检验，但未检出效应量或 95% 置信区间。",
                     "补充效应量与置信区间，避免只依据点估计或 p 值下结论。",
                     _last_body_anchor(document, r"(检验|显著性|p\\s*[<=>]|结果)") or anchors, "R-09")]''',
)
text = text.replace(
    '''    return [_problem("R-10", Severity.MID, "缺少重复实验与方差报告",
                     "报告了性能指标，但未检出重复次数、标准差/方差或置信区间。",
                     "报告重复次数与均值±标准差（或置信区间），并说明计算方式。", anchors, "R-10")]''',
    '''    return [_problem("R-10", Severity.MID, "缺少重复实验与方差报告",
                     "报告了性能指标，但未检出重复次数、标准差/方差或置信区间。",
                     "报告重复次数与均值±标准差（或置信区间），并说明计算方式。",
                     _first_body_anchor(document, r"(主结果|结果|性能)") or anchors, "R-10")]''',
)
text = text.replace(
    '''    if HYPER_SEARCH_SIGNAL.search(body_text):
        return [_problem("R-12", Severity.MID, "仅说明搜索方法，未给出搜索范围/候选空间",
                         "文中提到超参数搜索方法，但未检出搜索范围或候选取值集合。",
                         "补充每个超参数的搜索范围与候选空间，并说明最终取值依据。", anchors, "R-12")]''',
    '''    if HYPER_SEARCH_SIGNAL.search(body_text):
        return [_problem("R-12", Severity.MID, "仅说明搜索方法，未给出搜索范围/候选空间",
                         "文中提到超参数搜索方法，但未检出搜索范围或候选取值集合。",
                         "补充每个超参数的搜索范围与候选空间，并说明最终取值依据。",
                         _first_body_anchor(document, r"(超参数|学习率|批量大小|Dropout|权重衰减|卷积核)") or anchors, "R-12")]''',
)
text = text.replace(
    '''    model_index = _paragraph_matching(document, re.compile(r"(训练|模型|评估|交叉验证|微调)"), last=True)
    anchor_list = [_anchor(model_index)] if model_index is not None else anchors
    return [_problem("R-14"''',
    '''    anchor_list = _first_body_anchor(document, r"(训练细节|优化器|学习率|批量大小|Dropout|权重衰减)") or anchors
    return [_problem("R-14"''',
)

path.write_text(text, encoding="utf-8")
print("锚点优化已应用")
