"""盲测修复：论文类型识别接入 + 角标数学上标过滤 + R-01/R-10/R-12 模式补充。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"

# 1) schemas：ReviewReport / ReviewCreateResponse 增加 paper_type
schemas = APP / "models" / "schemas.py"
text = schemas.read_text(encoding="utf-8")
text = text.replace(
    "    figure_references: int = 0\n    demote_on_figures: bool = False\n",
    "    figure_references: int = 0\n    demote_on_figures: bool = False\n    paper_type: str = \"unknown\"\n",
)
text = text.replace(
    "    figure_references: int = 0\n    demote_on_figures: bool = False\n\n\nclass ReportSummary",
    "    figure_references: int = 0\n    demote_on_figures: bool = False\n    paper_type: str = \"unknown\"\n\n\nclass ReportSummary",
)
schemas.write_text(text, encoding="utf-8")

# 2) docx_parser：只接受“引用样式”的上标（过滤数学上标）
parser = APP / "parsers" / "docx_parser.py"
text = parser.read_text(encoding="utf-8")
if "CITATION_BRACKET" not in text:
    text = text.replace(
        'REFERENCE_ITEM = re.compile(r"^\\s*\\[?(\\d+)\\]?[\\.\\、\\．\\:\\)]?\\s+")',
        'REFERENCE_ITEM = re.compile(r"^\\s*\\[?(\\d+)\\]?[\\.\\、\\．\\:\\)]?\\s+")\n'
        'CITATION_BRACKET = re.compile(r"^\\[\\s*[\\d\\s,，\\-–—]+\\s*\\]$")\n'
        'BARE_CITATION = re.compile(r"^\\d{1,3}$")\n'
        'MATH_PREV = set(")]}〉」】‖|·×+-=/")',
    )
    text = text.replace(
        "def split_sentences(text: str) -> list[Sentence]:",
        '''def is_citation_span(span: str, prev_char: str, next_char: str) -> bool:
    """仅把“引用样式”的上标当作角标，过滤 R²、O((d+1)³)、‖·‖² 等数学上标。"""
    span = span.strip()
    if not span:
        return False
    if CITATION_BRACKET.match(span):
        return True
    if BARE_CITATION.match(span):
        if prev_char and (prev_char.isalnum() or prev_char in MATH_PREV):
            return False
        if next_char and next_char in MATH_PREV + "%":
            return False
        return True
    return False


def split_sentences(text: str) -> list[Sentence]:''',
    )
    text = text.replace(
        """            current: list[str] = []
            for part, is_sup, _ in runs:
                if is_sup:
                    current.append(part)
                elif current:
                    sup_spans.append((index, "".join(current)))
                    current = []
            if current:
                sup_spans.append((index, "".join(current)))""",
        """            buffer = ""
            current: list[str] = []
            for part, is_sup, _ in runs:
                if is_sup:
                    current.append(part)
                    continue
                if current:
                    span = "".join(current)
                    if is_citation_span(span, buffer[-1] if buffer else "", part[:1]):
                        sup_spans.append((index, span))
                    current = []
                buffer += part
            if current:
                span = "".join(current)
                if is_citation_span(span, buffer[-1] if buffer else "", ""):
                    sup_spans.append((index, span))""",
    )
    parser.write_text(text, encoding="utf-8")
    print("docx_parser 已加入角标过滤")

# 3) reviewer：按论文类型裁剪清单 + 记录 paper_type
reviewer = APP / "engine" / "reviewer.py"
text = reviewer.read_text(encoding="utf-8")
text = text.replace(
    "from app.engine.prompts import build_review_prompt",
    "from app.engine.paper_type import REVIEW_ALLOWED_ITEMS, classify\nfrom app.engine.prompts import build_review_prompt",
)
text = text.replace(
    "    started = time.monotonic()\n    elements = extract_elements(document)\n    rule_findings = run_rules(document, elements)\n    notes: list[str] = []",
    "    started = time.monotonic()\n    paper_type, type_evidence = classify(document)\n    items_for_review = (\n        [item for item in items if item.id in REVIEW_ALLOWED_ITEMS] if paper_type == \"review\" else items\n    )\n    notes: list[str] = []\n    if paper_type == \"review\":\n        skipped = len(items) - len(items_for_review)\n        notes.append(\n            f\"识别为综述/理论论文（非实证）：已跳过 {skipped} 条实证类检查（如数据划分/基线/消融/统计检验/可复现性）。\"\n        )\n    elements = extract_elements(document)\n    rule_findings = run_rules(document, elements)",
)
text = text.replace(
    "                llm_findings, usage, invalid = _llm_findings(document, items, provider)",
    "                llm_findings, usage, invalid = _llm_findings(document, items_for_review, provider)",
)
text = text.replace(
    "    findings = _attach_evidence(merged, items, elements, _rule_anchors(rule_findings))",
    "    findings = _attach_evidence(merged, items_for_review, elements, _rule_anchors(rule_findings))",
)
text = text.replace(
    "        notes=notes,\n        figure_references=len(figure_references),",
    "        notes=notes,\n        paper_type=paper_type,\n        figure_references=len(figure_references),",
)
reviewer.write_text(text, encoding="utf-8")

# 4) elements：目标表述 + 交叉验证（重复实验）
elements = APP / "engine" / "elements.py"
text = elements.read_text(encoding="utf-8")
text = text.replace(
    '        r"(本文旨在|研究目标|研究问题|我们研究|本文的目标|本研究的目的)",',
    '        r"(本文旨在|研究目标|研究问题|我们研究|本文的目标|本研究的目的|本文以|系统阐述|系统梳理|本文综述|本文回顾|旨在|目的是|目标在于)",',
)
text = text.replace(
    '        r"(重复实验|重复\\s*\\d+\\s*次|均值\\s*±\\s*标准差|多次运行|折交叉验证)",',
    '        r"(重复实验|重复\\s*\\d+\\s*次|均值\\s*±\\s*标准差|多次运行|折交叉验证|交叉验证)",',
)
elements.write_text(text, encoding="utf-8")

# 5) rules：超参搜索依据补充“交叉验证确定”
rules = APP / "engine" / "rules.py"
text = rules.read_text(encoding="utf-8")
text = text.replace(
    '"调参|取值范围|grid\\s*search"',
    '"调参|取值范围|交叉验证确定|通过交叉验证|由交叉验证|grid\\s*search"',
)
rules.write_text(text, encoding="utf-8")

# 6) 路由响应：paper_type 透出
route = APP / "api" / "routes_review.py"
text = route.read_text(encoding="utf-8")
text = text.replace('        "figure_references": report.figure_references,', '        "figure_references": report.figure_references,\n        "paper_type": report.paper_type,')
route.write_text(text, encoding="utf-8")

print("盲测修复应用完成")
