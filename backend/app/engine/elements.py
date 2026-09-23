"""方法学要素抽取（中英双语词表；规则优先，证据门控的基础）。

所有要素都带原文锚点；模型判定必须挂到这些要素上，无证据不得出结论。
"""

import re

from app.core.ids import new_id
from app.models.schemas import Anchor, DocumentIR, Element

PATTERNS: dict[str, list[str]] = {
    "sample_size": [
        r"\d[\d,]{1,}\s*(?:例|名|个|份|张|人)",
        r"\d[\d,]{1,}\s*(?:患者|样本|图像|图片|受试者|被试|病例|问卷|受试)",
        r"\b\d[\d,]{2,}\s*(?:patients?|subjects?|samples?|images?|cases?|participants?|scans?|studies|volunteers?|records?)\b",
        r"\b\d[\d,]{2,}\b[^.\n]{0,25}?(?:patients?|subjects?|samples?|images?|cases?|participants?|scans?|volunteers?|records?)\b",
        r"\b[nN]\s*=\s*\d[\d,]*",
    ],
    "sample_size_rationale": [
        r"(样本量.{0,6}依据|功效分析|统计学功效|把握度)",
        r"(power\s*analysis|power\s*calculation|sample\s*size\s*(?:justification|calculation|estimation)|a\s*priori\s*sample)",
    ],
    "data_split": [
        r"(训练集|验证集|测试集|测试集合|独立测试集|数据划分|划分\s*为|交叉验证|留出法|分层\s*\d+\s*折)",
        r"(训练\s*/\s*验证\s*/\s*测试|训练\s*/\s*验证|验证\s*/\s*测试|训练\s*/\s*测试|train\s*/\s*val(?:idation)?\s*/\s*test)",
        r"(随机种子|random\s*seed|random\s*state|\bseed\s*[=:]\s*\d+)",
        r"(train(?:ing)?\s*(?:set|split|data)|validation\s*set|test\s*set|hold[\s-]?out|k[\s-]?fold|split\s*(?:the\s*data|into))",
    ],
    "study_design": [
        r"(随机对照|队列研究|回顾性|前瞻性|横断面|实验设计|实验设置|基准数据集|数据集)",
        r"(cohort|retrospective|prospective|cross[\s-]?sectional|randomi[sz]ed|benchmark|dataset|survey|experiment(al)?\s*design)",
    ],
    "research_goal": [
        r"(本文旨在|研究目标|研究问题|我们研究|本文的目标|本研究的目的|本文以|系统阐述|系统梳理|本文综述|本文回顾|旨在|目的是|目标在于)",
        r"(we\s+aim|this\s+study\s+aims?|research\s+question|we\s+investigate|objective\s+of\s+this\s+study)",
    ],
    "stat_test": [
        r"(t\s*检验|配对\s*t|Wilcoxon|Mann[-\s]?Whitney|ANOVA|卡方|Fisher|McNemar|Kruskal|Spearman|Pearson|DeLong|χ2|χ²|χ\s*2)"
        r"|(Hosmer[-\s]?Lemeshow|log[-\s]?rank|bootstrap|置换检验|显著性检验|统计检验|线性混合|混合效应|随机效应|Benjamini|Hochberg|FDR|逻辑回归|多元逻辑|回归分析|logistic)",
        r"(t[\s-]?test|paired\s+t|wilcoxon|mann[\s-]?whitney|\banova\b|chi[\s-]?squared?|fisher'?s|mcnemar|kruskal[\s-]?wallis|spearman|pearson|delong|hosmer[\s-]?lemeshow|log[\s-]?rank|bootstrap|permutation\s+test|mixed[\s-]?effects|linear\s+mixed|benjamini|hochberg|\bfdr\b|logistic\s+regression|regression\s+analysis)",
    ],
    "p_value": [r"p\s*[<=>]\s*0?\.\d+", r"\bp\s*[<=>]\s*\.\d+", r"\bp[\s-]?value"],
    "confidence_interval": [
        r"(95%\s*(?:置信区间|CI)|置信区间)",
        r"(95%\s*ci|confidence\s*interval|\bci\s*[:=]?\s*[\[\(]?\s*0?\.\d+)",
    ],
    "effect_size": [
        r"(效应量|Cohen)",
        r"(effect\s*size|cohen'?s\s*d|eta\s*squared|odds\s*ratio|hazard\s*ratio|\bOR\s*=\s*[\d.]+|\bHR\s*=\s*[\d.]+)",
    ],
    "metric": [
        r"(准确率|精确率|召回率|准确度|正确率|敏感度|特异度|评价指标|评估指标|性能|表现|误差|一致性|曲线下面积)",
        r"(\baccuracy\b|\bprecision\b|\brecall\b|\bsensitivity\b|\bspecificity\b|\bf1\b|\bauc\b|\brmse\b|\bmae\b|\bssim\b|\bdice\b|\biou\b|balanced\s*accuracy)",
    ],
    "baseline": [
        r"(基线|对比方法|对照组|比较方法|基准|与先前|与已有|与现有)",
        r"(baseline|state[\s-]?of[\s-]?the[\s-]?art|\bsota\b|comparison\s+method|control\s+group|prior\s+method|existing\s+method|compared\s+(?:with|to|against))",
    ],
    "ablation": [r"(消融|ablation)"],
    "hyperparameter": [
        r"(超参数|学习率|批大小|网格搜索|随机搜索|早停|搜索空间|优化器|正则化系数|正则化参数|惩罚系数)",
        r"(hyper[\s-]?parameter|learning\s*rate|batch\s*size|grid\s*search|random\s*search|early\s*stopping|optimizer|regularization\s*(?:coefficient|parameter))",
    ],
    "preprocessing": [
        r"(归一化|标准化|数据增强|类别不平衡|过采样|欠采样|重采样|预处理|滤波)",
        r"(normalization|normalisation|standardization|standardisation|data\s*augmentation|class\s*imbalance|oversampling|undersampling|resampling|preprocessing)",
    ],
    "reproducibility": [
        r"(随机种子|复现|数据可得|数据可用|代码(?:已)?开源|开源代码)",
        r"(random\s*seed|\bseed\s*[=:]\s*\d+|code\s+(?:is\s+)?(?:available|released)|data\s+(?:are\s+)?available|reproducib)",
    ],
    "limitation": [
        r"(局限|不足之处|未来工作|伦理|合规声明|后续工作|讨论其局限|开放问题|开放挑战|尚未解决|待解决|未来方向|展望|研究空白|挑战)",
        r"(limitation|limitations|future\s*work|shortcoming|constraint|ethical\s+(?:consideration|approval))",
    ],
    "multiple_comparison": [
        r"(多重比较|错误发现率)",
        r"(multiple\s*comparison|bonferroni|holm|benjamini|hochberg|\bfdr\b|false\s*discovery\s*rate|correction\s*for\s*multiple)",
    ],
    "repeats": [
        r"(重复实验|重复\s*\d+\s*次|均值\s*±\s*标准差|多次运行|折交叉验证|交叉验证)",
        r"(repeated\s*(?:experiment|run|measurement)s?|mean\s*±\s*sd|standard\s*deviation|fold\s*cross[\s-]?validation|repeated\s+\d+\s*times)",
        r"\d+(?:\.\d+)?\s*±\s*\d+(?:\.\d+)?",
    ],
    "conclusion": [
        r"(结论|结果表明|综合上述|综上)",
        r"(in\s*conclusion|we\s*conclude|these\s*results\s*(?:show|suggest|indicate)|overall)",
    ],
    "overgeneralization": [
        r"(普遍适用|普适|推广至各类|广泛适用|均可适用|适用于所有)",
        r"(generally\s*applicable|broadly\s*applicable|can\s*be\s*generalized|generaliz(?:able|ed)\s*to|universally\s*applicable|all\s*types\s*of)",
    ],
    "novel_module": [
        r"(本文提出|我们提出|改进(?:的)?模块|注意力机制|新增模块|关键模块)",
        r"(we\s*propose|we\s*introduce|our\s*(?:new|proposed)|attention\s*mechanism|novel\s*module|key\s*module|proposed\s*(?:model|framework|architecture))",
    ],
}


def extract_elements(document: DocumentIR) -> list[Element]:
    elements: list[Element] = []
    if document.citations:
        elements.append(
            Element(
                id=new_id("E"),
                type="citation",
                value=f"{len(document.citations)} 个引用角标",
                anchors=[document.citations[0].anchor],
                confidence=1.0,
            )
        )
    if document.references:
        elements.append(
            Element(
                id=new_id("E"),
                type="reference_list",
                value=f"{len(document.references)} 条参考文献",
                anchors=[document.references[0].anchor],
                confidence=1.0,
            )
        )
    for paragraph in document.paragraphs:
        units = paragraph.sentences or []
        if units:
            for sentence in units:
                elements.extend(_match_sentence(paragraph.index, sentence.index, sentence.text))
        else:
            elements.extend(_match_sentence(paragraph.index, None, paragraph.text))
    return elements


def _match_sentence(paragraph_index: int, sentence_index: int | None, text: str) -> list[Element]:
    matched: list[Element] = []
    for element_type, patterns in PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                matched.append(
                    Element(
                        id=new_id("E"),
                        type=element_type,
                        value=text.strip()[:160],
                        anchors=[Anchor(paragraph_index=paragraph_index, sentence_index=sentence_index)],
                        confidence=0.8,
                    )
                )
                break
    return matched


def elements_of_type(elements: list[Element], element_type: str) -> list[Element]:
    return [element for element in elements if element.type == element_type]


def has_element(elements: list[Element], element_type: str) -> bool:
    return any(element.type == element_type for element in elements)
