"""规则增强（针对预埋缺陷类论文）：
R-07 需具名检验；R-04 单一基线；R-08 多数据集/多模型；R-06 分类指标；
R-12 需搜索范围；R-03 泄漏=测试集调参 + 划分细节（比例/折数/种子）。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
rules = ROOT / "backend" / "app" / "engine" / "rules.py"
text = rules.read_text(encoding="utf-8")

# 1) 新增模式常量
if "NAMED_TEST_PATTERN" not in text:
    text = text.replace(
        'TEST_SET_PATTERN = re.compile(r"(测试集|test\\s*set)", re.IGNORECASE)',
        'NAMED_TEST_PATTERN = re.compile(\n'
        '    r"(t\\s*检验|配对\\s*t|Wilcoxon|Mann[-\\s]?Whitney|ANOVA|卡方|χ2|χ²|Fisher|McNemar|Kruskal|Spearman|Pearson|"\n'
        '    r"DeLong|Hosmer[-\\s]?Lemeshow|log[-\\s]?rank|bootstrap|置换检验|线性混合|混合效应|随机效应|"\n'
        '    r"Benjamini|Hochberg|FDR|逻辑回归|logistic\\s+regression|t[-\\s]?test|paired\\s+t|wilcoxon|anova)", re.IGNORECASE)\n'
        'LEAK_ON_TEST_PATTERN = re.compile(\n'
        '    r"(测试集[^。；，]{0,12}(调参|调优|调超参|选择超参数|模型选择|网格搜索)|\n'
        '    (调参|模型选择|超参数选择|网格搜索)[^。；，]{0,12}(基于|使用|利用|在)?测试集)", re.IGNORECASE | re.VERBOSE)\n'
        'SPLIT_DETAIL_PATTERN = re.compile(\n'
        '    r"(\\d+\\s*[:：]\\s*\\d+|\\d+\\s*/\\s*\\d+(?:\\s*/\\s*\\d+)?|\\d+\\s*%|(一|二|三|四|五|六|七|八|九|十)\\s*折|\\d+\\s*折|k\\s*折|"\n'
        '    r"交叉验证|随机种子\\s*[=为]?\\s*\\d+|seed\\s*[=:]\\s*\\d+)", re.IGNORECASE)\n'
        'MULTI_BASELINE_PATTERN = re.compile(\n'
        '    r"(\\d+\\s*(个|种|类)\\s*(基线|对比方法|对照)|多个基线|多种基线|若干基线|多条基线|\\d+\\s*(个|种)[^。；]{0,20}(模型|方法)[^。；]{0,10}(比较|对比))", re.IGNORECASE)\n'
        'SINGLE_BASELINE_PATTERN = re.compile(\n'
        '    r"(以[^，。；]{1,24}作为(对比)?基线|仅(与|以)[^，。；]{1,24}(比较|作为基线)|对比方法(仅|只)?为[^，。；]{1,24})", re.IGNORECASE)\n'
        'HYPER_RANGE_PATTERN = re.compile(r"(\\[|取值范围|搜索范围|范围\\s*[\\[（(]|搜索空间|候选(集|值)|离散取值|\\{[^}]{1,40}\\})")\n'
        'CLASSIFICATION_TASK_PATTERN = re.compile(r"(文本分类|分类任务|分类模型|文本类别|text\\s*classification)", re.IGNORECASE)\n'
        'CLASSIFICATION_METRIC_PATTERN = re.compile(\n'
        '    r"(准确率|精度|精确率|召回率|宏平均|macro[-\\s]?f1|\\bF1\\b|\\bAUC\\b|混淆矩阵|正确率|F1值)", re.IGNORECASE)',
    )

# 2) R-07：需具名检验
old07 = '''    if has_element(elements, "stat_test"):
        return [_pass("R-07", "已说明统计检验方法", "R-07", _anchor_for(elements, "stat_test"))]'''
new07 = '''    if NAMED_TEST_PATTERN.search(_document_text(document)):
        return [_pass("R-07", "已说明统计检验方法", "R-07", _anchor_for(elements, "stat_test", "p_value"))]'''
if old07 in text:
    text = text.replace(old07, new07)
    print("R-07 已改为需具名检验")

# 3) R-06：分类任务需有分类指标
old06 = '''    if has_element(elements, "metric"):
        return [_pass("R-06", "已报告评价指标", "R-06", anchors)]'''
new06 = '''    body_text = _document_text(document)
    if CLASSIFICATION_TASK_PATTERN.search(body_text) and not CLASSIFICATION_METRIC_PATTERN.search(body_text):
        return [_problem("R-06", Severity.MID, "未报告与分类任务匹配的性能指标",
                         "论文为分类任务，但未检出准确率/精确率/召回率/F1 等分类性能指标（可能只报告了工程指标）。",
                         "补充与任务匹配的分类指标（如准确率、macro-F1），并说明指标选择依据。", anchors, "R-06")]
    if has_element(elements, "metric"):
        return [_pass("R-06", "已报告评价指标", "R-06", anchors)]'''
if old06 in text:
    text = text.replace(old06, new06)
    print("R-06 已加分类指标校验")

# 4) R-04：单一基线判定
old04 = '''    if MULTI_MODEL_SIGNAL.search(_document_text(document)):
        return [_pass("R-04", "存在多模型对比", "R-04", anchors)]'''
new04 = '''    body_text = _document_text(document)
    if MULTI_MODEL_SIGNAL.search(body_text) or MULTI_BASELINE_PATTERN.search(body_text):
        return [_pass("R-04", "存在多模型对比", "R-04", anchors)]
    if SINGLE_BASELINE_PATTERN.search(body_text):
        model_index = _paragraph_matching(document, re.compile(r"(模型|方法|基线)"), last=True)
        anchor_list = [_anchor(model_index)] if model_index is not None else anchors
        return [_problem("R-04", Severity.MID, "基线对比不完整（仅与单一模型比较）",
                         "全文仅检出 1 个对比基线，缺少其他近两年公开基线与经典方法，难以判断性能来源。",
                         "补充至少 2 个近期公开基线与 1 个经典方法，并统一数据划分与评价指标。",
                         anchor_list, "R-04")]'''
if old04 in text:
    text = text.replace(old04, new04)
    print("R-04 已加单一基线判定")

# 5) R-12：需搜索范围/候选空间
old12 = '''    if HYPER_SEARCH_SIGNAL.search(_document_text(document)):
        return [_pass("R-12", "已说明超参数选择依据", "R-12", anchors)]'''
new12 = '''    body_text = _document_text(document)
    if HYPER_SEARCH_SIGNAL.search(body_text) and HYPER_RANGE_PATTERN.search(body_text):
        return [_pass("R-12", "已说明超参数选择依据", "R-12", anchors)]
    if HYPER_SEARCH_SIGNAL.search(body_text):
        return [_problem("R-12", Severity.MID, "仅说明搜索方法，未给出搜索范围/候选空间",
                         "文中提到超参数搜索方法，但未检出搜索范围或候选取值集合。",
                         "补充每个超参数的搜索范围与候选空间，并说明最终取值依据。", anchors, "R-12")]'''
if old12 in text:
    text = text.replace(old12, new12)
    print("R-12 已加搜索范围校验")

# 6) R-03：泄漏=测试集调参；并新增“划分细节”校验
old03 = '''        if (
            LEAKAGE_PATTERN.search(paragraph.text)
            and TEST_SET_PATTERN.search(paragraph.text)
            and not PROPER_USE_PATTERN.search(paragraph.text)
        ):'''
new03 = '''        if LEAK_ON_TEST_PATTERN.search(paragraph.text):'''
if old03 in text:
    text = text.replace(old03, new03)
    print("R-03 泄漏判据已改为“测试集调参”")

old03b = '''    if has_element(elements, "data_split"):
        return [_pass("R-03", "已描述数据划分", "R-03", anchors)]'''
new03b = '''    if has_element(elements, "data_split"):
        if SPLIT_DETAIL_PATTERN.search(_document_text(document)):
            return [_pass("R-03", "已描述数据划分", "R-03", anchors)]
        return [_problem("R-03", Severity.HIGH, "未描述具体数据划分比例与随机种子",
                         "文中提到训练/验证/测试集，但未给出划分比例（或折数）与随机种子。",
                         "补充划分比例（如 8:1:1）或交叉验证折数，并写明随机种子以保障可复现。",
                         anchors, "R-03")]'''
if old03b in text:
    text = text.replace(old03b, new03b)
    print("R-03 已加“划分比例/种子”校验")

# 7) R-08：多数据集/多模型信号扩展
old08 = 'MULTI_COMPARISON_SIGNAL = re.compile(r"(\\d+\\s*种.{0,30}模型|多个模型|多种模型|多组学|富集分析|通路|多个数据集|多种方法|多种指标)")'
new08 = 'MULTI_COMPARISON_SIGNAL = re.compile(r"(\\d+\\s*种.{0,30}模型|\\d+\\s*(个|种)[^。；]{0,20}(数据集|模型)|多个模型|多种模型|多组学|富集分析|通路|多个数据集|多种方法|多种指标|跨数据集)")'
if old08 in text:
    text = text.replace(old08, new08)
    print("R-08 信号已扩展")

rules.write_text(text, encoding="utf-8")
print("规则增强完成")
