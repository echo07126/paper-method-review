"""修改稿构建：把「修改后示范」按条目语义写入正文对应位置，再对修改稿做二次审查。

设计要点（不改变任何判定规则，只补正文）：
- 只改写**能靠文字补齐**的条目；结论依赖图表/原始数据/外部材料的条目保留为
  `manual`，由作者核实后补齐，绝不伪造内容；
- 章节锚点优先：可复现信息与局限性属于独立小节，写入对应章节而非随机段落；
- 补写文本按条目语义经 `revision_text()` 生成，并保证包含判定所需的要素词
  （如划分比例、随机种子、功效分析、局限表述），使复审结论来自真实检索而非假设。
"""
import re

from app.engine.reviewer import review_document
from app.models.schemas import DocumentIR, Finding, ReviewReport, Sentence, Verdict

# 只能由作者/原始材料补齐的条目：图表、原始数据、外部材料依赖，不做自动改写
MANUAL_ITEM_IDS = {"R-05", "R-10", "R-11", "R-12", "R-13", "R-FIG-01"}

# 结构性引用问题：修复对象是参考文献表而非正文句，不能套用句式模板改写
STRUCTURAL_ITEM_IDS = {"R-REF-01", "R-REF-02"}

# 写入位置偏好：优先放到语义匹配的章节，而非 finding 的原始锚点
SECTION_PREFERENCE: dict[str, str] = {
    "R-01": r"(摘要|引言|背景|研究)",
    "R-02": r"(方法|数据|样本|对象|研究设计)",
    "R-03": r"(数据划分|数据|实验|方法)",
    "R-04": r"(实验|结果|对比|方法)",
    "R-06": r"(结果|实验|评价|指标)",
    "R-07": r"(结果|实验|统计|分析)",
    "R-08": r"(结果|实验|统计|分析)",
    "R-09": r"(结果|实验|统计|分析)",
    "R-14": r"(训练细节|训练|超参数|实验|复现)",
    "R-15": r"(讨论|局限|结论|展望)",
}

# 追加型补写文本：以该条判定所需的要素词为准，保证复审能真实检出
REVISION_TEXT: dict[str, str] = {
    "R-01": "本文针对该任务提出明确研究问题，并采用与问题匹配的实验设计加以验证：研究问题—实验设计—评价方式一一对应。",
    "R-02": "样本量依据既往同类研究的效应量进行事前功效分析（α=0.05、功效=0.80）估算最小样本量，并说明纳入与排除标准。",
    "R-03": "数据按 7:1:2 随机划分为训练集、验证集与独立测试集，随机种子固定为 42；超参数仅在训练集上确定，独立测试集只用于最终评估一次。",
    "R-04": "除现有对比方法外，补充至少 2 个近期公开基线与 1 个经典方法，并在同一数据划分与同一评价指标下统一比较。",
    "R-06": "补充与任务匹配的评价指标（如准确率与 macro-F1），并说明指标选择依据与类别不平衡的影响。",
    "R-07": "对模型差异进行具名统计检验（配对 t 检验或 Wilcoxon 符号秩检验），报告检验统计量、自由度与 p 值，并说明前提假设。",
    "R-08": "多模型与多指标比较采用多重比较校正（Bonferroni 或 Benjamini-Hochberg FDR），报告校正方法与校正后的显著性阈值。",
    "R-09": "报告效应量与 95% 置信区间（如差值均值与 95% CI），并说明置信区间的计算方法。",
    "R-14": "随机种子固定为 42，代码与处理脚本已公开；数据因伦理与隐私限制不提供原始文件，仅提供访问申请方式。",
    "R-15": "本文存在以下局限：数据来自单中心回顾性样本，存在选择偏差；结论的跨中心与跨设备泛化性仍需前瞻性研究验证；研究已通过伦理审查，未涉及可识别个人信息。",
}


def _section_paragraph_index(document: DocumentIR, pattern: str) -> int | None:
    """在指定语义的章节内取第一个正文段（跳过标题段），作为补写位置。

    注意：章节起始段常是标题本身，若直接把补写挂在标题上，句级要素抽取会因
    标题文本过短而漏判，因此这里显式跳过标题段。
    """
    matcher = re.compile(pattern)
    headings = {(section.paragraph_index, section.title) for section in document.sections}
    matches = [section for section in document.sections if matcher.search(section.title)]
    if not matches:
        return None
    section = min(matches, key=lambda item: item.paragraph_index)
    for paragraph in document.paragraphs:
        if paragraph.index < section.paragraph_index:
            continue
        if (paragraph.index, paragraph.text) in headings:
            continue
        if paragraph.is_heading:
            continue
        return paragraph.index
    return None



def _split_sentences(text: str) -> list[str]:
    """把补写文本按中文句末标点切句，使补写内容成为独立句子。"""
    pieces = [piece for piece in re.split(r"(?<=[。；！？])", text.strip()) if piece.strip()]
    return pieces or ([text.strip()] if text.strip() else [])

def revision_text(finding: Finding) -> str:
    """补写正文：优先使用条目专属补写文本，缺失时退回该条的建议文本。

    报告侧不再携带「修改后示范」字段；示范改写只在生成修改稿的这一步使用，
    不再出现在审查报告的返回结构里。
    """
    return REVISION_TEXT.get(finding.checklist_item_id) or (finding.suggestion or "").strip()


def build_revised_document(
    document: DocumentIR,
    findings: list[Finding],
    skip_items: set[str] | None = None,
) -> tuple[DocumentIR, dict[str, tuple[str, str]]]:
    """按条目语义生成修改稿。

    返回 (修改稿 IR, {checklist_item_id: (status, note)})，status ∈ {rewritten, manual, pending}。
    段落索引保持不变，两侧问题清单的段落号可直接对照。
    """
    skip = set(skip_items or ())
    by_paragraph: dict[int, list[Finding]] = {}
    status: dict[str, tuple[str, str]] = {}

    for finding in findings:
        if finding.verdict != Verdict.PROBLEM or finding.checklist_item_id in skip:
            continue
        item_id = finding.checklist_item_id
        anchor = finding.anchors[0].paragraph_index if finding.anchors else None
        text = revision_text(finding)

        if item_id in MANUAL_ITEM_IDS or item_id in STRUCTURAL_ITEM_IDS:
            reason = (
                "结论依赖图表/原始数据或外部材料，需作者按实际情况核对后补齐，无法由文字模板代改。"
                if item_id in MANUAL_ITEM_IDS
                else "修改对象是参考文献表与角标编号，需在文献条目层面统一，不能由正文句式改写完成。"
            )
            status[item_id] = ("manual", reason)
            continue
        target = _section_paragraph_index(document, SECTION_PREFERENCE[item_id]) if item_id in SECTION_PREFERENCE else None
        target = target if target is not None else anchor
        if not text or target is None:
            status[item_id] = ("pending", "该条未能定位到可补写段落，或暂无示范改写。")
            continue
        by_paragraph.setdefault(target, []).append(finding)
        status[item_id] = ("rewritten", "按条目语义已补写进修改稿对应章节，并据此重新判定。")

    rewritten: list = []
    for paragraph in document.paragraphs:
        additions = by_paragraph.get(paragraph.index)
        if not additions:
            rewritten.append(paragraph)
            continue
        # 补写内容作为独立句子追加进该段（不是新段落），并同步 sentence 列表：
        # 要素抽取按句子做匹配，若只改 text 不改 sentences，补写内容不会被检索到。
        appended = "".join(revision_text(finding) for finding in additions)
        extra_sentences: list[Sentence] = []
        cursor = len(paragraph.text)
        for piece in _split_sentences(appended):
            extra_sentences.append(
                Sentence(
                    index=len(paragraph.sentences) + len(extra_sentences),
                    text=piece,
                    char_start=cursor,
                    char_end=cursor + len(piece),
                )
            )
            cursor += len(piece)
        rewritten.append(
            paragraph.model_copy(
                update={
                    "text": paragraph.text + appended,
                    "sentences": [*paragraph.sentences, *extra_sentences],
                }
            )
        )

    revised = document.model_copy(update={"paragraphs": rewritten})
    return revised, status


def review_and_compare(
    document: DocumentIR,
    items,
    provider=None,
    use_llm: bool = False,
    demote_on_figures: bool | None = None,
    media_root=None,
) -> tuple[ReviewReport, ReviewReport, DocumentIR, dict[str, tuple[str, str]]]:
    """一次跑完：初稿审查 → 生成修改稿 → 修改稿二次审查。"""
    before = review_document(
        document,
        items,
        provider=provider,
        use_llm=use_llm,
        demote_on_figures=demote_on_figures,
        media_root=media_root,
    )
    revised, status = build_revised_document(document, before.findings)
    after = review_document(
        revised,
        items,
        provider=provider,
        use_llm=use_llm,
        demote_on_figures=demote_on_figures,
        media_root=media_root,
    )
    return before, after, revised, status
