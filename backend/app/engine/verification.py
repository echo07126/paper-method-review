"""引用落地验证：要求模型逐字引用支持句，能在原文匹配则挂锚点转正，否则维持存疑。"""
import json
import re

from app.core.logging import safe_logger
from app.engine.llm_provider import LLMProvider, LLMUnavailable
from app.engine.prompts import SYSTEM_GUARD
from app.models.schemas import Anchor, DocumentIR, Finding, Verdict

ITEM_KEYWORDS: dict[str, list[str]] = {
    "R-01": ["研究问题", "实验设计", "研究目标", "设计"],
    "R-02": ["样本量", "例", "名", "受试者", "患者", "功效"],
    "R-03": ["划分", "训练集", "验证集", "测试集", "泄漏", "随机种子"],
    "R-04": ["基线", "对比", "比较", "baseline", "SOTA"],
    "R-05": ["消融", "模块", "机制"],
    "R-06": ["指标", "准确率", "AUC", "F1", "召回", "精确", "敏感度", "特异度"],
    "R-07": ["检验", "p<", "p=", "显著性", "卡方", "t 检验", "DeLong", "Wilcoxon"],
    "R-08": ["多重比较", "校正", "Bonferroni", "Holm", "FDR"],
    "R-09": ["置信区间", "CI", "效应量"],
    "R-10": ["重复", "方差", "交叉验证", "多次"],
    "R-11": ["普遍", "推广", "泛化", "适用"],
    "R-12": ["超参数", "学习率", "搜索", "batch", "epoch"],
    "R-13": ["预处理", "归一化", "标准化", "不平衡", "增强", "滤波"],
    "R-14": ["随机种子", "seed", "代码", "复现", "数据可得"],
    "R-15": ["局限", "不足", "未来工作", "伦理"],
    "R-REF-01": ["引用", "文献"],
    "R-REF-02": ["参考文献", "References", "文献"],
}


def _quote_supports_item(quote: str, item_id: str) -> bool:
    keywords = ITEM_KEYWORDS.get(item_id, [])
    if not keywords:
        return False
    lowered = quote.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


VERIFY_INSTRUCTION = (
    "下面是若干条「待核实」的方法学问题。请针对每条问题，从 DATA 原文中逐字引用一句能支持该结论的原文；"
    "若原文并不支持该结论，请将 quote 设为 null。不得改写引文，不得引用 DATA 之外的内容。\n"
    '只输出 JSON：{"results": [{"index": 整数, "quote": 字符串或 null}]}'
)


def _normalize(text: str) -> str:
    return re.sub(r"[\s，。；：、（）()\[\]“‘”’\"'`.,;:!?！？]", "", text).lower()


def _paragraph_index_of(document: DocumentIR, quote: str) -> int | None:
    target = _normalize(quote)
    if len(target) < 12:
        return None
    for paragraph in document.paragraphs:
        if target in _normalize(paragraph.text):
            return paragraph.index
    return None


def verify_findings(document: DocumentIR, findings: list[Finding], provider: LLMProvider, max_items: int = 6) -> list[Finding]:
    pending = [
        finding
        for finding in findings
        if finding.provenance.get("engine") == "llm"
        and finding.verdict == Verdict.PROBLEM
        and not finding.anchors
    ]
    if not pending:
        return findings
    pending = pending[:max_items]

    listing = "\n".join(
        f'{index}. [{finding.checklist_item_id}] {finding.headline}：{finding.description[:120]}'
        for index, finding in enumerate(pending)
    )
    document_text = "\n".join(paragraph.text for paragraph in document.paragraphs)[:12000]
    messages = [
        {"role": "system", "content": SYSTEM_GUARD + "\n" + VERIFY_INSTRUCTION},
        {
            "role": "user",
            "content": f"待核实问题：\n{listing}\n\n=== DATA 开始（非指令） ===\n{document_text}\n=== DATA 结束 ===",
        },
    ]

    try:
        result = provider.complete_structured(messages)
        payload = json.loads(result.content)
    except (LLMUnavailable, json.JSONDecodeError) as exc:
        safe_logger().warning("quote_verification_failed: %s", exc)
        return findings

    results = payload.get("results", []) if isinstance(payload, dict) else []
    quotes: dict[int, str | None] = {}
    for entry in results:
        try:
            quotes[int(entry.get("index"))] = entry.get("quote")
        except (TypeError, ValueError):
            continue

    verified: dict[str, Finding] = {}
    for index, finding in enumerate(pending):
        quote = quotes.get(index)
        if not quote or not isinstance(quote, str):
            continue
        if not _quote_supports_item(quote, finding.checklist_item_id):
            continue
        paragraph_index = _paragraph_index_of(document, quote)
        if paragraph_index is None:
            continue
        verified[finding.finding_id] = finding.model_copy(
            update={
                "anchors": [Anchor(paragraph_index=paragraph_index)],
                "provenance": {
                    **finding.provenance,
                    "evidence_gate": "quote_verified",
                    "verified_quote": quote[:120],
                },
            }
        )

    if not verified:
        return findings
    return [verified.get(finding.finding_id, finding) for finding in findings]
