"""论文类型识别：区分「实证研究」与「综述/理论」论文，避免对非实证论文做实证类检查。"""
import re

from app.models.schemas import DocumentIR

REVIEW_SIGNAL = re.compile(
    r"(综述|文献综述|研究进展|系统梳理|系统阐述|系统介绍|理论基础|方法综述|原理与应用|"
    r"survey|systematic review|review|tutorial|overview)",
    re.IGNORECASE,
)
STRONG_REVIEW_SIGNAL = re.compile(r"(综述|研究进展|系统梳理|系统阐述|survey|review|tutorial|overview)", re.IGNORECASE)
EMPIRICAL_SIGNAL = re.compile(
    r"(实验组|数据集|样本量|受试者|患者|病例|基线|消融实验|测试集|验证集|训练集|准确率|"
    r"AUC|F1|敏感度|特异度|p\s*[<=>]\s*0?\.\d+|置信区间|随机种子|超参数|网格搜索|"
    r"dataset|baseline|ablation|accuracy|cohort|patients|subjects|random seed)",
    re.IGNORECASE,
)

REVIEW_ALLOWED_ITEMS = {"R-01", "R-15", "R-REF-01", "R-REF-02"}


def classify(document: DocumentIR) -> tuple[str, dict]:
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    titles = " ".join(section.title for section in document.sections[:5])
    review_hits = len(REVIEW_SIGNAL.findall(text))
    strong_hits = len(STRONG_REVIEW_SIGNAL.findall(text))
    empirical_hits = len(EMPIRICAL_SIGNAL.findall(text))
    title_strong = bool(STRONG_REVIEW_SIGNAL.search(titles))
    title_weak = bool(REVIEW_SIGNAL.search(titles))

    evidence = {
        "review_hits": review_hits,
        "strong_hits": strong_hits,
        "empirical_hits": empirical_hits,
        "title_strong": title_strong,
        "title_weak": title_weak,
    }

    if title_strong or strong_hits >= 2 or (title_weak and empirical_hits <= 3) or (review_hits >= 3 and empirical_hits <= review_hits):
        return "review", evidence
    if empirical_hits >= 3:
        return "empirical", evidence
    return "unknown", evidence
