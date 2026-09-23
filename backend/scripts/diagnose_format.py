"""格式压力测试：检验解析器对标题样式、语言、角标的鲁棒性。"""
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from docx import Document  # noqa: E402

from app.engine.elements import extract_elements  # noqa: E402
from app.engine.rules import run_rules  # noqa: E402
from app.parsers.registry import parse_document  # noqa: E402

EN_PARAS = [
    "We evaluated the proposed model on 1,240 fundus images, split into training and test sets.",
    "We compared against the baseline ResNet-50 and reported 95% confidence interval.",
    "A paired t-test showed a significant difference (p < 0.05).",
    "We set the random seed to 42 and released the code.",
    "We conducted an ablation study on the attention module.",
    "Limitations are discussed in the final section.",
]


def build(path: Path, use_styles: bool, english: bool) -> None:
    doc = Document()
    if use_styles:
        doc.add_heading("2. Methods", level=1)
    else:
        para = doc.add_paragraph()
        run = para.add_run("2. Methods")
        run.bold = True
    for text in (EN_PARAS if english else [
        "本研究纳入 1,240 例样本，按 8:2 划分为训练集与测试集。",
        "与基线方法 ResNet-50 比较，并报告 95% 置信区间。",
        "配对 t 检验显示差异显著（p<0.05），随机种子设为 42。",
        "对注意力模块进行了消融实验，并在末节讨论局限性。",
    ]):
        doc.add_paragraph(text)
    doc.save(path)


with tempfile.TemporaryDirectory() as tmp:
    cases = [
        ("中文 + Heading 样式", True, False),
        ("中文 + 仅加粗标题", False, False),
        ("英文 + Heading 样式", True, True),
        ("英文 + 仅加粗标题", False, True),
    ]
    for name, use_styles, english in cases:
        path = Path(tmp) / f"{name}.docx"
        build(path, use_styles, english)
        document = parse_document(path, path.name, None)
        elements = Counter(element.type for element in extract_elements(document))
        findings = [f for f in run_rules(document) if f.verdict.value == "problem"]
        print(f"=== {name}")
        print(f"    章节识别={len(document.sections)}  段落={len(document.paragraphs)}")
        print(f"    要素={dict(elements)}")
        print(f"    问题条目={sorted({f.checklist_item_id for f in findings})}")
