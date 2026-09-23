import re

from app.core.ids import new_id
from app.engine.elements import elements_of_type, extract_elements, has_element
from app.models.schemas import Anchor, DocumentIR, Element, Finding, Severity, Verdict

LEAKAGE_PATTERN = re.compile(r"(网格搜索|随机搜索|调参|超参数|模型选择)")
NAMED_TEST_PATTERN = re.compile(
    r"(t\s*检验|配对\s*t|Wilcoxon|Mann[-\s]?Whitney|ANOVA|卡方|χ2|χ²|Fisher|McNemar|Kruskal|Spearman|Pearson|"
    r"DeLong|Hosmer[-\s]?Lemeshow|log[-\s]?rank|bootstrap|置换检验|线性混合|混合效应|随机效应|"
    r"Benjamini|Hochberg|FDR|逻辑回归|logistic\s+regression|t[-\s]?test|paired\s+t|wilcoxon|anova)", re.IGNORECASE)
LEAK_ON_TEST_PATTERN = re.compile(
    r"(测试集[^。；，]{0,12}(调参|调优|调超参|选择超参数|模型选择|网格搜索)|"
    r"(调参|模型选择|超参数选择|网格搜索)[^。；，]{0,12}(基于|使用|利用|在)?测试集)",
    re.IGNORECASE,
)
SPLIT_DETAIL_PATTERN = re.compile(
    r"(\d+\s*[:：]\s*\d+|\d+\s*/\s*\d+(?:\s*/\s*\d+)?|\d+\s*%|(一|二|三|四|五|六|七|八|九|十)\s*折|\d+\s*折|k\s*折|"
    r"交叉验证|随机种子\s*[=为]?\s*\d+|seed\s*[=:]\s*\d+)", re.IGNORECASE)
MULTI_BASELINE_PATTERN = re.compile(
    r"(\d+\s*(个|种|类)\s*(基线|对比方法|对照)|多个基线|多种基线|若干基线|多条基线|\d+\s*(个|种)[^。；]{0,20}(模型|方法)[^。；]{0,10}(比较|对比))", re.IGNORECASE)
SINGLE_BASELINE_PATTERN = re.compile(
    r"(以[^，。；]{1,24}作为(对比)?基线|仅(与|以)[^，。；]{1,24}(比较|作为基线)|对比方法(仅|只)?为[^，。；]{1,24})", re.IGNORECASE)
HYPER_RANGE_PATTERN = re.compile(r"(\[|取值范围|搜索范围|范围\s*[\[（(]|搜索空间|候选(集|值)|离散取值|\{[^}]{1,40}\})")
CLASSIFICATION_TASK_PATTERN = re.compile(r"(文本分类|分类任务|分类模型|文本类别|text\s*classification)", re.IGNORECASE)
CLASSIFICATION_METRIC_PATTERN = re.compile(
    r"(准确率|精度|精确率|召回率|宏平均|macro[-\s]?f1|\bF1\b|\bAUC\b|混淆矩阵|正确率|F1值)", re.IGNORECASE)
PROPER_USE_PATTERN = re.compile(r"(测试集.{0,12}(仅|只|一次性).{0,12}(用|使用|评估|评价)|test\s*set.{0,20}(used\s*once|only\s*for\s*final))", re.IGNORECASE)
TRAINING_PATTERN = re.compile(r"(训练|交叉验证|微调|fine[-\s]?tun|pretrain|预训练)", re.IGNORECASE)
MULTI_COMPARISON_SIGNAL = re.compile(r"(\d+\s*种.{0,30}模型|\d+\s*(个|种)[^。；]{0,20}(数据集|模型)|多个模型|多种模型|多组学|富集分析|通路|多个数据集|多种方法|多种指标|跨数据集)")
MULTI_MODEL_SIGNAL = re.compile(r"(\d+\s*种.{0,30}模型|多个模型|多种模型)")
BASELINE_SIGNAL = re.compile(r"(基线|baseline|对比方法|对照组|比较方法|基准|与先前|与已有|与现有)", re.IGNORECASE)
ML_EVIDENCE_PATTERN = re.compile(r"(深度学习|机器学习|神经网络|卷积|Transformer|CNN|LSTM|ResNet|U-?net|分类器|模型训练|模型评估|训练集|测试集)", re.IGNORECASE)


def _anchor(paragraph_index: int) -> Anchor:
    return Anchor(paragraph_index=paragraph_index)


def _anchor_of(element: Element) -> Anchor:
    return element.anchors[0] if element.anchors else Anchor(paragraph_index=0)


def _make(item_id, verdict, severity, headline, description, suggestion, anchors, rule_id) -> Finding:
    return Finding(
        finding_id=new_id("F"), checklist_item_id=item_id, verdict=verdict, severity=severity,
        headline=headline, description=description, anchors=anchors, suggestion=suggestion,
        provenance={"engine": "rule", "rule_id": rule_id},
    )


def _problem(item_id, severity, headline, description, suggestion, anchors, rule_id) -> Finding:
    return _make(item_id, Verdict.PROBLEM, severity, headline, description, suggestion, anchors, rule_id)


def _pass(item_id, headline, rule_id, anchors, description="") -> Finding:
    return _make(item_id, Verdict.PASS, Severity.LOW, headline, description, "", anchors, rule_id)


def _section_body_anchor(document: DocumentIR, section_pattern: str, text_pattern: str | None = None):
    """在指定小节内取第一个（或任意）匹配的正文段作为锚点。"""
    section_re = re.compile(section_pattern)
    text_re = re.compile(text_pattern) if text_pattern else None
    def _heading_level(paragraph) -> int:
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
            continue
        if not inside or paragraph.style == "Table":
            continue
        if text_re is None or text_re.search(paragraph.text):
            return [_anchor(paragraph.index)]
    return []


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
        if not paragraph.is_heading
        and paragraph.style != "Table"
        and not re.match(r"^\s*\[\d+\]", paragraph.text)
        and compiled.search(paragraph.text)
    ]
    return [_anchor(hits[-1])] if hits else []


def _anchor_for(elements: list[Element], *types: str) -> list[Anchor]:
    for element_type in types:
        found = elements_of_type(elements, element_type)
        if found:
            return [_anchor_of(found[0])]
    return []


def _document_text(document: DocumentIR) -> str:
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _has_metric(elements: list[Element]) -> bool:
    return has_element(elements, "metric")


def _model_evidence(document: DocumentIR) -> bool:
    return bool(ML_EVIDENCE_PATTERN.search(_document_text(document)))


def _trains_model(document: DocumentIR, elements: list[Element]) -> bool:
    return has_element(elements, "data_split") or bool(TRAINING_PATTERN.search(_document_text(document)))


def _ai_empirical(document: DocumentIR, elements: list[Element]) -> bool:
    """AI 实证场景：既有性能指标，又有模型/训练证据（问卷、纯生物实验不满足）。"""
    return has_element(elements, "novel_module") or (_has_metric(elements) and _model_evidence(document))


def _last_paragraph_index(document: DocumentIR) -> int:
    return max((paragraph.index for paragraph in document.paragraphs), default=0)


def _paragraph_matching(document: DocumentIR, pattern: re.Pattern, last: bool = False) -> int | None:
    matches = [paragraph.index for paragraph in document.paragraphs if pattern.search(paragraph.text)]
    if not matches:
        return None
    return matches[-1] if last else matches[0]


def rule_dangling_citations(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    findings: list[Finding] = []
    for citation in document.citations:
        if citation.unresolved:
            findings.append(_problem("R-REF-01", Severity.LOW, f"存在悬空引用：编号 {citation.unresolved}",
                                     f"正文角标 {citation.text} 指向的文献在文末参考文献列表中不存在。",
                                     "请核对参考文献编号，补齐缺失条目或修正角标。", [citation.anchor], "R-REF-01"))
    if document.citations and not findings:
        findings.append(_pass("R-REF-01", "引用编号均可对账", "R-REF-01", [document.citations[0].anchor]))
    return findings


def rule_missing_references(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    if not document.citations:
        return []
    if document.references:
        return [_pass("R-REF-02", "参考文献章节存在", "R-REF-02", [document.references[0].anchor])]
    return [_problem("R-REF-02", Severity.MID, "正文含引用角标，但未识别到参考文献列表",
                     "解析结果中文末参考文献为空，可能是缺失该章节或解析失败。",
                     "请确认文末包含「参考文献/References」章节，或手动修正章节边界后重试。",
                     [_anchor(document.citations[0].anchor.paragraph_index)], "R-REF-02")]


def rule_data_split(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    if not (_trains_model(document, elements) or _ai_empirical(document, elements)):
        return []
    anchors = _anchor_for(elements, "data_split", "metric", "novel_module", "study_design")
    if not anchors:
        return []
    leakage: list[Finding] = []
    for paragraph in document.paragraphs:
        # 仅当“调参/模型选择”与“测试集”同时出现、且未声明“测试集仅用于最终评估”时，才判为泄漏；
        # 在验证集上调参属于规范做法，不应误报。
        if LEAK_ON_TEST_PATTERN.search(paragraph.text):
            leakage.append(_problem("R-03", Severity.HIGH, "疑似在验证/测试集上调参（信息泄漏风险）",
                                    f"原文：「{paragraph.text.strip()[:80]}…」在评估集相关语句中出现调参/模型选择描述。",
                                    "改为在训练集（或训练+验证）上调参，独立测试集只评估一次，并写明随机种子。",
                                    [_anchor(paragraph.index)], "R-03"))
    if leakage:
        return leakage
    if has_element(elements, "data_split"):
        split_paragraphs = [
            p.text
            for p in document.paragraphs
            if re.search(r"(划分|训练集|验证集|测试集|交叉验证)", p.text)
        ]
        if any(SPLIT_DETAIL_PATTERN.search(t) for t in split_paragraphs):
            return [_pass("R-03", "已描述数据划分", "R-03", anchors)]
        return [_problem("R-03", Severity.HIGH, "未描述具体数据划分比例与随机种子",
                         "文中提到训练/验证/测试集，但未给出划分比例（或折数）与随机种子。",
                         "补充划分比例（如 8:1:1）或交叉验证折数，并写明随机种子以保障可复现。",
                         (_section_body_anchor(document, r"(数据划分|数据划分与验证)", r"(划分|训练集|验证集|测试集|交叉验证)")
         or _section_body_anchor(document, r"(数据|实验|方法)", r"(划分|训练集|验证集|测试集|交叉验证)")) or anchors, "R-03")]
    anchor_list = (_section_body_anchor(document, r"(数据划分|数据划分与验证)", r"(划分|训练集|验证集|测试集|交叉验证)")
         or _section_body_anchor(document, r"(数据|实验|方法)", r"(划分|训练集|验证集|测试集|交叉验证)")) or anchors
    return [_problem("R-03", Severity.HIGH, "未描述数据划分/验证方案",
                     "文中涉及模型训练与评估，但未检出数据集划分或交叉验证方案说明。",
                     "补充训练/验证/测试集划分方式与随机种子；若使用交叉验证请说明折数与划分层级。",
                     anchor_list, "R-03")]


def rule_stat_test_missing(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    if not has_element(elements, "p_value"):
        return []
    if NAMED_TEST_PATTERN.search(_document_text(document)):
        return [_pass("R-07", "已说明统计检验方法", "R-07", _anchor_for(elements, "stat_test", "p_value"))]
    return [_problem("R-07", Severity.HIGH, "报告了 p 值但未说明统计检验方法",
                     "文中出现 p 值表述，但未检出具体的统计检验描述。",
                     "补充所用检验方法、检验对象与自由度，并说明前提假设是否满足。",
                     _last_body_anchor(document, r"(p\s*[<=>]\s*0?\.\d+|检验|显著性)") or _anchor_for(elements, "p_value"), "R-07")]


def rule_ci_missing(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    anchors = _anchor_for(elements, "stat_test", "p_value", "metric")
    if not anchors:
        return []
    if has_element(elements, "confidence_interval"):
        return [_pass("R-09", "已报告置信区间", "R-09", anchors)]
    return [_problem("R-09", Severity.MID, "缺少效应量或置信区间",
                     "报告了性能指标或显著性检验，但未检出效应量或 95% 置信区间。",
                     "补充效应量与置信区间，避免只依据点估计或 p 值下结论。",
                     _section_body_anchor(document, r"(统计检验|显著性|统计)", r"(检验|显著性|p\s*[<>=])") or anchors, "R-09")]


def rule_sample_size_rationale(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    anchors = _anchor_for(elements, "sample_size", "study_design")
    if not anchors:
        return []
    if has_element(elements, "sample_size_rationale"):
        return [_pass("R-02", "已说明样本量依据", "R-02", anchors)]
    return [_problem("R-02", Severity.LOW, "缺少样本量确定依据",
                     "检出研究队列/样本描述，但未见功效分析或样本量依据说明。",
                     "补充样本量确定依据（功效分析或数据可得性限制）与纳入/排除标准。", anchors, "R-02")]


def rule_reproducibility(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    if not (_trains_model(document, elements) or _ai_empirical(document, elements)):
        return []
    anchors = _anchor_for(elements, "data_split", "study_design", "novel_module") or [_anchor(0)]
    if has_element(elements, "reproducibility"):
        return [_pass("R-14", "已报告可复现信息", "R-14", anchors)]
    anchor_list = _section_body_anchor(document, r"(训练细节|训练|超参数)", r"(学习率|批量大小|Dropout|权重衰减|优化器|训练)") or anchors
    return [_problem("R-14", Severity.LOW, "缺少随机种子等可复现信息",
                     "存在模型训练/数据划分描述，但未检出随机种子、代码或数据可得性说明。",
                     "补充随机种子设置与代码/数据获取方式，提升可复现性。", anchor_list, "R-14")]


def rule_multiple_comparison(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    if not _ai_empirical(document, elements):
        return []
    if not MULTI_COMPARISON_SIGNAL.search(_document_text(document)):
        return []
    signal_index = _paragraph_matching(document, MULTI_COMPARISON_SIGNAL, last=True)
    anchors = [_anchor(signal_index)] if signal_index is not None else (_anchor_for(elements, "baseline", "metric") or [_anchor(0)])
    if has_element(elements, "multiple_comparison"):
        return [_pass("R-08", "已说明多重比较处理", "R-08", anchors)]
    return [_problem("R-08", Severity.MID, "多模型/多通路比较未见多重比较校正",
                     "文中存在多模型或多组学通路比较，但未见多重比较校正说明（如 Bonferroni / FDR）。",
                     "说明是否进行多重比较校正，并报告校正后的显著性。", anchors, "R-08")]


def rule_baseline_comparison(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    if not _ai_empirical(document, elements):
        return []
    anchors = _anchor_for(elements, "novel_module", "metric", "study_design", "baseline")
    if not anchors:
        return []
    body_text = _document_text(document)
    if MULTI_MODEL_SIGNAL.search(body_text) or MULTI_BASELINE_PATTERN.search(body_text):
        return [_pass("R-04", "存在多模型对比", "R-04", anchors)]
    if SINGLE_BASELINE_PATTERN.search(body_text):
        anchor_list = (_section_body_anchor(document, r"(基线方法|基线|对比方法)", r"(基线|对比方法|对照|baseline)")
         or _first_body_anchor(document, r"(基线|对比方法|对照)")) or anchors
        return [_problem("R-04", Severity.MID, "基线对比不完整（仅与单一模型比较）",
                         "全文仅检出 1 个对比基线，缺少其他近两年公开基线与经典方法，难以判断性能来源。",
                         "补充至少 2 个近期公开基线与 1 个经典方法，并统一数据划分与评价指标。",
                         anchor_list, "R-04")]
    if any(BASELINE_SIGNAL.search(paragraph.text) for paragraph in document.paragraphs):
        return [_pass("R-04", "已列出基线方法", "R-04", anchors)]
    model_index = _paragraph_matching(document, re.compile(r"(模型|方法|网络)"), last=True)
    anchor_list = [_anchor(model_index)] if model_index is not None else anchors
    return [_problem("R-04", Severity.MID, "基线对比不完整",
                     "文中未检出可核对的基线方法（如 baseline / 对比方法 / 对照组 / 与先前方法比较）。",
                     "补充至少 2 个近期公开基线与 1 个经典方法，并统一数据划分与评价指标。",
                     anchor_list, "R-04")]


def rule_ablation_missing(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    if not has_element(elements, "novel_module"):
        return []
    anchors = _section_body_anchor(document, r"(模型结构|方法|模型)", r"(本文提出|改进的注意力|改进的模块|多尺度卷积层|模型由)") or _anchor_for(elements, "novel_module")
    if has_element(elements, "ablation"):
        return [_pass("R-05", "已包含消融实验", "R-05", anchors)]
    return [_problem("R-05", Severity.MID, "声称的关键模块缺少消融实验",
                     "文中提到本文提出的模块/机制，但未检出消融实验描述。",
                     "对每个声称有贡献的模块做有/无对照，并说明默认设置依据。", anchors, "R-05")]


def rule_overgeneralization(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    if not has_element(elements, "overgeneralization"):
        return []
    return [_problem("R-11", Severity.LOW, "结论存在外推过度风险",
                     "检出「普遍适用 / 推广至各类」等表述，可能超出数据与实验条件范围。",
                     "限定结论适用范围，并把泛化性验证列入局限与未来工作。",
                     _anchor_for(elements, "overgeneralization"), "R-11")]


def rule_limitation_missing(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    if len(document.paragraphs) < 4:
        return []
    if has_element(elements, "limitation"):
        return [_pass("R-15", "已包含局限讨论", "R-15", _anchor_for(elements, "limitation"))]
    anchor_list = _section_body_anchor(document, r"(讨论|局限|结论)", None) or [
        _anchor(max([p.index for p in document.paragraphs if p.style != "Table"], default=0))
    ]
    return [_problem("R-15", Severity.LOW, "未见局限性讨论",
                     "全文未检出「局限 / 不足 / 未来工作 / 开放问题 / 伦理」相关讨论。",
                     "补充局限性章节，说明数据范围、泛化性、开放问题与伦理合规边界。",
                     anchor_list, "R-15")]


INTRO_SIGNAL = re.compile(r"(摘要|abstract|引言|introduction|背景|background)", re.IGNORECASE)
HYPER_SEARCH_SIGNAL = re.compile(
    r"(网格搜索|随机搜索|搜索空间|超参数搜索|调参|取值范围|交叉验证确定|通过交叉验证|由交叉验证|grid\s*search|random\s*search|search\s*space|hyper[\s-]?parameter\s*(?:search|tuning)|tuned)",
    re.IGNORECASE,
)


def _has_intro(document: DocumentIR) -> bool:
    return any(INTRO_SIGNAL.search(section.title) for section in document.sections)


def rule_research_goal(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    """R-01 仅在检测到摘要/引言章节（完整论文）时评估，避免节选样本误报。"""
    if not _has_intro(document):
        return []
    anchors = _anchor_for(elements, "study_design", "metric", "novel_module") or [_anchor(0)]
    if has_element(elements, "research_goal"):
        return [_pass("R-01", "已明确研究目标/问题", "R-01", anchors)]
    return [_problem("R-01", Severity.MID, "未明确研究问题或目标",
                     "检测到论文包含摘要/引言章节，但未检出明确的研究目标或研究问题表述。",
                     "在引言末尾明确研究问题与假设，并说明与实验设计的对应关系。", anchors, "R-01")]


def rule_metric_reported(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    """R-06：提出模型/模块却没有任何性能指标时提示。"""
    if not has_element(elements, "novel_module"):
        return []
    anchors = (
        _section_body_anchor(document, r"(评价指标|评估指标|指标)", None)
        or _section_body_anchor(document, r"(模型结构|方法)", r"(模块|机制|注意力)")
        or _anchor_for(elements, "novel_module")
    )
    body_text = _document_text(document)
    if CLASSIFICATION_TASK_PATTERN.search(body_text) and not CLASSIFICATION_METRIC_PATTERN.search(body_text):
        return [_problem("R-06", Severity.MID, "未报告与分类任务匹配的性能指标",
                         "论文为分类任务，但未检出准确率/精确率/召回率/F1 等分类性能指标（可能只报告了工程指标）。",
                         "补充与任务匹配的分类指标（如准确率、macro-F1），并说明指标选择依据。", anchors, "R-06")]
    if has_element(elements, "metric"):
        return [_pass("R-06", "已报告评价指标", "R-06", anchors)]
    return [_problem("R-06", Severity.MID, "未报告评价指标",
                     "文中提出模型/模块，但未检出性能指标（准确率 / AUC / F1 / RMSE 等）。",
                     "补充与任务匹配的评价指标，并说明指标选择依据。", anchors, "R-06")]


def rule_repeats_reported(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    """R-10：有性能指标但无重复次数/方差/置信区间。"""
    if not _ai_empirical(document, elements) or not has_element(elements, "metric"):
        return []
    anchors = _anchor_for(elements, "metric")
    if has_element(elements, "repeats") or has_element(elements, "confidence_interval"):
        return [_pass("R-10", "已报告重复次数或离散程度", "R-10", anchors)]
    return [_problem("R-10", Severity.MID, "缺少重复实验与方差报告",
                     "报告了性能指标，但未检出重复次数、标准差/方差或置信区间。",
                     "报告重复次数与均值±标准差（或置信区间），并说明计算方式。",
                     _section_body_anchor(document, r"(主结果|实验结果|结果)", None) or anchors, "R-10")]


def rule_hyperparameter_justification(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    """R-12：给出超参数但未说明搜索/选择依据。"""
    if not has_element(elements, "hyperparameter"):
        return []
    anchors = _anchor_for(elements, "hyperparameter")
    hyper_paragraphs = [
        p.text
        for p in document.paragraphs
        if re.search(r"(超参数|学习率|批量大小|批大小|Dropout|权重衰减|卷积核|搜索|调参|正则化系数|正则化参数)", p.text)
    ]
    body_text = _document_text(document)
    citation_stripped = [
        re.sub(r"\[\s*\d[\d\s,，\-–—]*\]", "", t) for t in hyper_paragraphs
    ]
    if HYPER_SEARCH_SIGNAL.search(_document_text(document)) and any(
        HYPER_RANGE_PATTERN.search(t) for t in citation_stripped
    ):
        return [_pass("R-12", "已说明超参数选择依据", "R-12", anchors)]
    if HYPER_SEARCH_SIGNAL.search(body_text):
        return [_problem("R-12", Severity.MID, "仅说明搜索方法，未给出搜索范围/候选空间",
                         "文中提到超参数搜索方法，但未检出搜索范围或候选取值集合。",
                         "补充每个超参数的搜索范围与候选空间，并说明最终取值依据。",
                         _section_body_anchor(document, r"(训练细节|超参数|训练)", r"(超参数|学习率|批量大小|Dropout|权重衰减|卷积核)") or anchors, "R-12")]
    return [_problem("R-12", Severity.MID, "仅给出超参数取值，未说明搜索/选择依据",
                     "检出超参数描述，但未见网格/随机搜索、搜索空间或调参依据说明。",
                     "补充搜索范围、搜索方法与最终取值依据。", anchors, "R-12")]


def rule_preprocessing_reported(document: DocumentIR, elements: list[Element]) -> list[Finding]:
    """R-13：AI 实证场景下缺少数据预处理/不平衡处理说明。"""
    if not _ai_empirical(document, elements):
        return []
    anchors = _anchor_for(elements, "metric", "novel_module", "data_split", "study_design") or [_anchor(0)]
    if has_element(elements, "preprocessing"):
        return [_pass("R-13", "已说明预处理/不平衡处理", "R-13", anchors)]
    return [_problem("R-13", Severity.MID, "缺少数据预处理与不平衡处理说明",
                     "未检出归一化/标准化、数据增强或类别不平衡处理等说明。",
                     "补充预处理流程与不平衡处理策略，避免影响可复现性。", anchors, "R-13")]


RULES = [
    rule_dangling_citations,
    rule_missing_references,
    rule_data_split,
    rule_stat_test_missing,
    rule_ci_missing,
    rule_sample_size_rationale,
    rule_reproducibility,
    rule_multiple_comparison,
    rule_baseline_comparison,
    rule_ablation_missing,
    rule_overgeneralization,
    rule_limitation_missing,
    rule_research_goal,
    rule_metric_reported,
    rule_repeats_reported,
    rule_hyperparameter_justification,
    rule_preprocessing_reported,
]


def run_rules(document: DocumentIR, elements: list[Element] | None = None) -> list[Finding]:
    resolved = elements if elements is not None else extract_elements(document)
    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule(document, resolved))
    return findings
