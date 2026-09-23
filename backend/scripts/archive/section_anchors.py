"""按章节定位锚点：先找到目标小节标题，再取其下第一个匹配的正文段。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "backend" / "app" / "engine" / "rules.py"
text = path.read_text(encoding="utf-8")

helper = '''
def _section_body_anchor(document: DocumentIR, section_pattern: str, text_pattern: str | None = None):
    """在指定小节内取第一个（或任意）匹配的正文段作为锚点。"""
    section_re = re.compile(section_pattern)
    text_re = re.compile(text_pattern) if text_pattern else None
    inside = False
    for paragraph in document.paragraphs:
        if paragraph.is_heading:
            if section_re.search(paragraph.text):
                inside = True
            elif inside:
                inside = False
            continue
        if not inside or paragraph.style == "Table":
            continue
        if text_re is None or text_re.search(paragraph.text):
            return [_anchor(paragraph.index)]
    return []


def _first_body_anchor(document: DocumentIR, pattern: str, skip_first: int = 3):'''
text = text.replace("\ndef _first_body_anchor(document: DocumentIR, pattern: str, skip_first: int = 3):", helper, 1)

# 各规则改用“章节内定位”
replacements = [
    # R-03 划分细节
    ('_last_body_anchor(document, r"(划分|训练集|验证集|测试集|交叉验证)")',
     '_section_body_anchor(document, r"(数据划分|数据|实验|方法)", r"(划分|训练集|验证集|测试集|交叉验证)")'),
    # R-04 单一基线
    ('_first_body_anchor(document, r"(基线方法|基线|对比方法|对照)")',
     '_section_body_anchor(document, r"(基线|对比|方法)", r"(基线|对比方法|对照)")'),
    # R-05 消融缺失
    ('_first_body_anchor(document, r"(本文提出|我们提出|改进的注意力|改进的模块|模型结构)")',
     '_section_body_anchor(document, r"(模型结构|方法|模型)", r"(本文提出|改进的注意力|改进的模块|多尺度卷积层|模型由)")'),
    # R-06 指标缺失
    ('_first_body_anchor(document, r"(评价指标|评估指标|度量方式)")',
     '_section_body_anchor(document, r"(评价指标|评估指标|指标)", None)'),
    ('_first_body_anchor(document, r"(模块|机制|注意力)")',
     '_section_body_anchor(document, r"(模型结构|方法)", r"(模块|机制|注意力)")'),
    # R-09 统计检验
    ('_last_body_anchor(document, r"(统计检验|显著性|p\\s*[<>=])")',
     '_section_body_anchor(document, r"(统计检验|显著性|统计)", r"(检验|显著性|p\\s*[<>=])")'),
    # R-10 重复与方差
    ('_first_body_anchor(document, r"(表\\s*[12]|主结果)")',
     '_section_body_anchor(document, r"(主结果|实验结果|结果)", None)'),
    # R-12 超参数范围
    ('_first_body_anchor(document, r"(超参数|学习率|批量大小|Dropout率|权重衰减|卷积核数)")',
     '_section_body_anchor(document, r"(训练细节|超参数|训练)", r"(超参数|学习率|批量大小|Dropout|权重衰减|卷积核)")'),
    # R-14 可复现
    ('_first_body_anchor(document, r"(训练细节|学习率|批量大小|Dropout|权重衰减)")',
     '_section_body_anchor(document, r"(训练细节|训练|超参数)", r"(学习率|批量大小|Dropout|权重衰减|优化器|训练)")'),
]
for old, new in replacements:
    if old in text:
        text = text.replace(old, new)
    else:
        print("  [skip]", old[:50])

# R-15：讨论/局限/结论小节
import re as _re
text = _re.sub(
    r"    anchor_list = _first_body_anchor\(document, r\"\(讨论\|局限\|结论\)\"\) or \[\n"
    r"        _anchor\(max\(\[p\.index for p in document\.paragraphs if p\.style != \"Table\"\], default=0\)\)\n"
    r"    \]",
    '    anchor_list = _section_body_anchor(document, r"(讨论|局限|结论)", None) or [\n'
    '        _anchor(max([p.index for p in document.paragraphs if p.style != "Table"], default=0))\n'
    '    ]',
    text,
)
path.write_text(text, encoding="utf-8")
print("章节锚点已应用")
