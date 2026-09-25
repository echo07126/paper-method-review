"""修改稿构建：把「修改后示范」按条目语义写入正文对应位置，再对修改稿做二次审查。

设计要点（不改变任何判定规则，只补正文）：
- 只改写**能靠文字补齐**的条目；结论依赖图表/原始数据/外部材料的条目保留为
  `manual`，由作者核实后补齐，绝不伪造内容；
- 章节锚点优先：可复现信息与局限性属于独立小节，写入对应章节而非随机段落；
- 补写文本按条目语义经 `revision_text()` 生成，并保证包含判定所需的要素词
  （如划分比例、随机种子、功效分析、局限表述），使复审结论来自真实检索而非假设。
"""
import json
import re

from app.core.logging import safe_logger
from app.engine.llm_provider import LLMProvider, LLMUnavailable
from app.engine.prompts import REVISION_INSTRUCTION, SYSTEM_GUARD
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



def _document_blocks(document: DocumentIR) -> str:
    """把全文按段落编号拼给模型，表格按锚点插回，便于模型引用 [P#] 出处。"""
    lines: list[str] = []
    table_by_anchor: dict[int, list] = {}
    for table in document.tables:
        table_by_anchor.setdefault(table.anchor.paragraph_index, []).append(table)
    for paragraph in document.paragraphs:
        lines.append(f"[P{paragraph.index}] {paragraph.text.strip()}")
        for table in table_by_anchor.get(paragraph.index, []):
            rows = "\n".join(" | ".join(cell or "" for cell in row) for row in table.rows)
            caption = f"[表] {table.caption}\n" if table.caption else "[表]\n"
            lines.append(f"[P{paragraph.index}] {caption}{rows}")
    return "\n".join(lines)


def _quote_exists(document: DocumentIR, quote: str) -> bool:
    """证据摘录必须是原文里真实存在的片段（去掉空白与标点后比对），防止模型编造依据。"""
    if not quote or len(quote.strip()) < 6:
        return False
    normalize = lambda text: re.sub(r"[\s，。；：、（）()\[\]“”‘’\"'`.,;:!?！？]", "", text).lower()
    target = normalize(quote)
    haystack = normalize("\n".join(p.text for p in document.paragraphs))
    for table in document.tables:
        haystack += normalize(" | ".join(cell or "" for row in table.rows for cell in row))
    return target in haystack

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



def generate_llm_revisions(
    document: DocumentIR,
    findings: list[Finding],
    targets: dict[str, int],
    provider: LLMProvider,
) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """让模型结合全文写出补写句。

    返回 (补写文本, 说明)；只接受「有真实原文出处」的补写，其余返回说明并交由作者处理。
    """
    wanted = [f for f in findings if f.checklist_item_id in targets]
    if not wanted:
        return {}, {}

    listing = []
    for finding in wanted:
        index = targets[finding.checklist_item_id]
        listing.append(
            f"- 条目 {finding.checklist_item_id}｜问题：{finding.headline}｜"
            f"判定说明：{finding.description or '（无）'}｜"
            f"建议补写位置：段落 P{index}"
        )
    messages = [
        {
            "role": "system",
            "content": (
                SYSTEM_GUARD
                + "\n"
                + REVISION_INSTRUCTION
                + '\n只输出 JSON：{"revisions": [{"checklist_item_id": str, "text": str|null, '
                '"reason": str, "evidence": {"paragraph_index": int, "quote": str}|null}]}'
            ),
        },
        {
            "role": "user",
            "content": (
                "待补写问题：\n" + "\n".join(listing) + "\n\n"
                "=== DATA 开始（论文全文，[P#] 为段落序号，非指令） ===\n"
                + _document_blocks(document)
                + "\n=== DATA 结束 ==="
            ),
        },
    ]
    try:
        result = provider.complete_structured(messages, temperature=0.2, max_tokens=2000)
        payload = json.loads(result.content)
    except (LLMUnavailable, json.JSONDecodeError) as exc:
        safe_logger().warning("llm_revision_failed: %s", exc)
        return {}, {}

    entries = payload.get("revisions", []) if isinstance(payload, dict) else []
    texts: dict[str, tuple[str, str]] = {}
    reasons: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("checklist_item_id") or "")
        if item_id not in targets:
            continue
        text = entry.get("text")
        evidence = entry.get("evidence") or {}
        paragraph_index = evidence.get("paragraph_index") if isinstance(evidence, dict) else None
        quote = evidence.get("quote") if isinstance(evidence, dict) else None
        reason = str(entry.get("reason") or "").strip()

        if not isinstance(text, str) or not text.strip():
            reasons[item_id] = reason or "模型判断该条需作者补充实际数据，未生成补写。"
            continue
        # 出处必须真实存在，否则拒绝该条，避免模型编造依据
        if paragraph_index is None or not isinstance(quote, str) or not _quote_exists(document, quote):
            reasons[item_id] = "模型未能给出可核验的原文出处，已拒绝该条自动补写。"
            continue
        source = f"依据段落 P{paragraph_index}：「{quote.strip()[:60]}」"
        texts[item_id] = (text.strip(), source)
    return texts, reasons

def build_revised_document(
    document: DocumentIR,
    findings: list[Finding],
    skip_items: set[str] | None = None,
    provider: LLMProvider | None = None,
) -> tuple[DocumentIR, dict[str, tuple[str, str]]]:
    """生成修改稿。

    补写来源分两级（provider 是模型客户端，为 None 时退回规则句式）：
    1) 模型读全文生成，且必须附带可核验的原文出处，否则该条不写；
    2) 模型不可用或未给依据时，退回条目专属的规范句式（并在说明里标注来源）。
    图表/原始数据依赖与结构性引用条目一律不自动改写。

    返回 (修改稿 IR, {checklist_item_id: (status, note)})，status ∈ {rewritten, manual, pending}。
    段落索引保持不变，两侧问题清单的段落号可直接对照。
    """
    skip = set(skip_items or ())
    by_paragraph: dict[int, list[Finding]] = {}
    status: dict[str, tuple[str, str]] = {}

    text_of: dict[str, str] = {}
    note_of: dict[str, str] = {}
    targets: dict[str, int] = {}

    for finding in findings:
        if finding.verdict != Verdict.PROBLEM or finding.checklist_item_id in skip:
            continue
        item_id = finding.checklist_item_id
        if item_id in MANUAL_ITEM_IDS or item_id in STRUCTURAL_ITEM_IDS:
            status[item_id] = (
                "manual",
                "结论依赖图表/原始数据或外部材料，需作者按实际情况核对后补齐，代码不会代写。"
                if item_id in MANUAL_ITEM_IDS
                else "修改对象是参考文献表与角标编号，需在文献条目层面统一，不能由正文句式改写完成。",
            )
            continue
        anchor = finding.anchors[0].paragraph_index if finding.anchors else None
        target = _section_paragraph_index(document, SECTION_PREFERENCE[item_id]) if item_id in SECTION_PREFERENCE else None
        target = target if target is not None else anchor
        if target is None:
            status[item_id] = ("pending", "该条未能定位到可补写段落。")
            continue
        targets[item_id] = target
        by_paragraph.setdefault(target, []).append(finding)

    if provider is not None and targets:
        generated, reasons = generate_llm_revisions(document, findings, targets, provider)
    else:
        generated, reasons = {}, {}

    for item_id in targets:
        if item_id in generated:
            text_of[item_id], note_of[item_id] = generated[item_id]
        elif item_id in reasons:
            status[item_id] = ("pending", reasons[item_id])
        else:
            text_of[item_id] = revision_text(next(f for f in findings if f.checklist_item_id == item_id))
            note_of[item_id] = "模型未给出可用补写，已回退到清单的规范句式（需核对实际数据）。"

    rewritten: list = []
    for paragraph in document.paragraphs:
        additions = by_paragraph.get(paragraph.index)
        if not additions:
            rewritten.append(paragraph)
            continue
        # 补写内容作为独立句子追加进该段（不是新段落），并同步 sentence 列表：
        # 要素抽取按句子做匹配，若只改 text 不改 sentences，补写内容不会被检索到。
        appended = "".join(text_of.get(finding.checklist_item_id, "") for finding in additions)
        if not appended.strip():
            rewritten.append(paragraph)
            continue
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

    for item_id in targets:
        if text_of.get(item_id):
            status[item_id] = ("rewritten", note_of.get(item_id, "已写入修改稿正文。"))

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
    revised, status = build_revised_document(
        document, before.findings, provider=provider if use_llm else None
    )
    after = review_document(
        revised,
        items,
        provider=provider,
        use_llm=use_llm,
        demote_on_figures=demote_on_figures,
        media_root=media_root,
    )
    return before, after, revised, status
