import json
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.ids import new_id
from app.core.config import get_settings
from app.core.logging import safe_logger
from app.engine.elements import extract_elements
from app.engine.figure_consistency import check_figure_consistency
from app.engine.figures import demote_for_figures, find_figure_references
from app.engine.llm_provider import LLMProvider, LLMUnavailable
from app.engine.numeric_consistency import check_numeric_consistency
from app.engine.paper_type import REVIEW_ALLOWED_ITEMS, classify
from app.engine.prompts import build_directed_review_prompt, build_review_prompt, limit_prompt_text
from app.engine.retrieval import build_index, directed_context
from app.engine.rules import run_rules, undetermined_finding
from app.engine.verification import verify_findings
from app.engine.vision import read_figure_values
from app.models.schemas import (
    Certainty,
    DocumentIR,
    Element,
    Finding,
    ReviewItem,
    ReviewReport,
    Severity,
    Verdict,
)

VERDICT_MAP = {
    "pass": Verdict.PASS,
    "problem": Verdict.PROBLEM,
    "not_applicable": Verdict.NOT_APPLICABLE,
    "uncertain": Verdict.UNCERTAIN,
}
SEVERITY_MAP = {"high": Severity.HIGH, "mid": Severity.MID, "low": Severity.LOW}

# —— 统一门控仲裁与输出质量量化 ——
# 各门控（证据门 / 判定主体档 / 图表降级 / 引用核验 / 图像识读）在流程中各自落一个
# provenance 标记；`_apply_gates` 是唯一读取这些标记、决定展示原因并量化置信度的地方。
# 展示原因的优先级（高 → 低）：一条结论同时命中多个门控标记时取最靠前者说明「为什么降级」。
GATE_PRIORITY = ("no_evidence", "vetoed_llm", "rule_anchor_reuse", "advisory", "figures_unparsed", "vision_read", "quote_verified")
# 门控因子：置信度取所有命中门控因子中的**最小值**（最保守），避免多门命中时被高因子掩盖。
GATE_FACTOR = {
    "no_evidence": 0.35,
    "vetoed_llm": 0.40,
    "rule_anchor_reuse": 0.85,
    "advisory": 0.60,
    "figures_unparsed": 0.60,
    "vision_read": 0.45,
    "quote_verified": 1.0,
    "direct": 1.0,
}
GATE_LABEL = {
    "direct": "规则直判",
    "not_evaluated": "未评估（证据不足）",
    "no_evidence": "无原文证据",
    "vetoed_llm": "规则否决模型",
    "rule_anchor_reuse": "复用规则锚点",
    "advisory": "顾问/建议档",
    "figures_unparsed": "图表未解析",
    "vision_read": "图像识读",
    "quote_verified": "引用已验证",
}
# 判据基分：确定性核验给满、规则侧疑似 0.8、模型疑似 0.6（模型精度低于结构与数值判据）。
BASE_CONFIDENCE = {"deterministic": 1.0, "rule": 0.8, "llm": 0.6}
# A/B/C/D 分档阈值：A ≥0.85 / B ≥0.60 / C ≥0.40 / 其余（含未能判定）为 D。
GRADE_THRESHOLDS = (0.85, 0.60, 0.40)


class LLMFindingPayload(BaseModel):
    """模型输出的严格契约：字段类型与枚举不合法即丢弃该条。"""

    model_config = ConfigDict(extra="ignore")

    checklist_item_id: str
    verdict: Literal["pass", "problem", "not_applicable", "uncertain"]
    severity: Literal["high", "mid", "low"] | None = None
    headline: str = ""
    description: str = ""
    suggestion: str = ""


def _counts(findings: list[Finding]) -> dict[str, int]:
    counts = {
        "high": 0, "mid": 0, "low": 0, "total": 0, "pass": 0, "not_applicable": 0, "uncertain": 0, "assessed": 0,
        "deterministic": 0, "suspected": 0, "undetermined": 0,
    }
    for finding in findings:
        counts[finding.certainty.value] = counts.get(finding.certainty.value, 0) + 1
        # 「已评估」只统计真正给出结论的条目；未能判定（undetermined）不计入。
        if finding.certainty != Certainty.UNDETERMINED:
            counts["assessed"] += 1
        if finding.verdict == Verdict.PROBLEM:
            counts[finding.severity.value] += 1
            counts["total"] += 1
        else:
            counts[finding.verdict.value] = counts.get(finding.verdict.value, 0) + 1
    return counts


def _required_types(items: list[ReviewItem]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for item in items:
        mapping[item.id] = [r.split(":", 1)[1] for r in item.requires if r.startswith("element:")]
    return mapping


def _rule_anchors(findings: list[Finding]) -> dict[str, list]:
    anchors: dict[str, list] = {}
    for finding in findings:
        if finding.provenance.get("engine") == "rule":
            anchors.setdefault(finding.checklist_item_id, []).extend(finding.anchors)
    return anchors


def _attach_evidence(
    findings: list[Finding],
    items: list[ReviewItem],
    elements: list[Element],
    rule_anchors: dict[str, list] | None = None,
) -> list[Finding]:
    required = _required_types(items)
    by_type: dict[str, list[Element]] = {}
    for element in elements:
        by_type.setdefault(element.type, []).append(element)

    gated: list[Finding] = []
    for finding in findings:
        matched: list[Element] = []
        for element_type in required.get(finding.checklist_item_id, []):
            matched.extend(by_type.get(element_type, [])[:1])

        evidence_ids = [element.id for element in matched]
        anchors = list(finding.anchors)
        for element in matched:
            anchors.extend(element.anchors)

        updates: dict = {"evidence_elements": evidence_ids}
        # Element.confidence 向上传递：仅规则引擎结论、且证据要素全部为结构级（confidence=1.0）时
        # 才升级为确定性核验；模型结论不因证据结构而获得确定性（certainty 只描述判据可靠性）。
        if (
            finding.provenance.get("engine") == "rule"
            and matched
            and all(element.confidence >= 1.0 for element in matched)
        ):
            updates["certainty"] = Certainty.DETERMINISTIC
        if anchors and not finding.anchors:
            updates["anchors"] = anchors[:3]

        if finding.provenance.get("engine") == "llm" and finding.verdict == Verdict.PROBLEM and not anchors:
            reused = (rule_anchors or {}).get(finding.checklist_item_id, [])
            if reused:
                updates["anchors"] = reused[:3]
                updates["provenance"] = {**finding.provenance, "evidence_gate": "rule_anchor_reuse"}
            else:
                updates["verdict"] = Verdict.UNCERTAIN
                updates["description"] = "[无原文证据，需人工复核] " + finding.description
                updates["provenance"] = {**finding.provenance, "evidence_gate": "no_evidence"}

        gated.append(finding.model_copy(update=updates))
    return gated


def _merge_findings(rule_findings: list[Finding], llm_findings: list[Finding]) -> list[Finding]:
    """规则结论为主、LLM 文本补充，冲突则记录。

    规则引擎对同一条目可能给出多条独立结论（如多条悬空引用、多段泄漏），必须全部保留，
    不得用 dict[checklist_item_id] 覆盖成一条；LLM 的补充文本合并到该条目的首条规则结论上。
    """
    merged: list[Finding] = list(rule_findings)
    first_index_by_item: dict[str, int] = {}
    for index, finding in enumerate(merged):
        first_index_by_item.setdefault(finding.checklist_item_id, index)
    extras: list[Finding] = []
    for finding in llm_findings:
        index = first_index_by_item.get(finding.checklist_item_id)
        if index is None or finding.checklist_item_id == "unknown":
            extras.append(finding)
            continue
        base = merged[index]
        vetoed = base.verdict == Verdict.PASS and finding.verdict == Verdict.PROBLEM
        merged[index] = base.model_copy(
            update={
                "description": base.description or finding.description,
                "suggestion": base.suggestion or finding.suggestion,
                "provenance": {
                    **base.provenance,
                    "merged_with_llm": True,
                    "llm_verdict": finding.verdict.value,
                    "conflict": base.verdict != finding.verdict,
                    "vetoed_llm": vetoed,
                },
            }
        )
    return merged + extras


def _apply_judge_tiers(findings: list[Finding], items: list[ReviewItem], force_advisory: bool) -> list[Finding]:
    """按条目 judge 档位分权：只有规则侧与 llm 档的模型结论可作为 problem。

    - judge=advisory 的条目：模型结论一律降级为「建议/存疑」（规则侧结论不受影响）；
    - judge=llm 的条目：模型可主导判定（能否成立另由证据门与门控仲裁决定）；
    - force_advisory（全局顾问模式安全阀）开启时，所有模型结论一律降级，行为与旧版一致。
    """
    judge_of = {item.id: item.judge for item in items}
    adjusted: list[Finding] = []
    for finding in findings:
        demote = finding.provenance.get("engine") == "llm" and finding.verdict == Verdict.PROBLEM and (
            force_advisory or judge_of.get(finding.checklist_item_id, "llm") == "advisory"
        )
        if demote:
            adjusted.append(
                finding.model_copy(
                    update={
                        "verdict": Verdict.UNCERTAIN,
                        "description": "[模型建议，需人工确认] " + finding.description,
                        "provenance": {**finding.provenance, "advisory": True},
                    }
                )
            )
        else:
            adjusted.append(finding)
    return adjusted


def _gate_flags(finding: Finding) -> list[str]:
    """一条结论命中的全部门控标记（用于取展示原因与最保守因子）。"""
    provenance = finding.provenance
    flags: list[str] = []
    evidence_gate = provenance.get("evidence_gate")
    if evidence_gate in GATE_FACTOR:
        flags.append(evidence_gate)
    if provenance.get("advisory") and "advisory" not in flags:
        flags.append("advisory")
    if provenance.get("vetoed_llm"):
        flags.append("vetoed_llm")
    return flags


def _gate_reason(flags: list[str]) -> str:
    for reason in GATE_PRIORITY:
        if reason in flags:
            return reason
    return "direct"


def _confidence_of(finding: Finding) -> float:
    """confidence = 判据基分 × 证据 × 一致性 × 门控因子（各因子取最保守值）。"""
    if finding.certainty == Certainty.UNDETERMINED:
        return 0.0
    base = BASE_CONFIDENCE.get(finding.provenance.get("engine"), 0.6)
    if finding.certainty == Certainty.DETERMINISTIC:
        base = BASE_CONFIDENCE["deterministic"]
    evidence = 1.0 if (finding.anchors or finding.evidence_elements) else 0.5
    consistency = 1.0
    if finding.provenance.get("dual_check") == "disagree":
        consistency = 0.6
    elif finding.provenance.get("conflict") and finding.verdict == Verdict.PROBLEM:
        consistency = 0.7
    gate = min((GATE_FACTOR[flag] for flag in _gate_flags(finding)), default=1.0)
    return round(max(0.0, min(1.0, base * evidence * consistency * gate)), 4)


def _grade_of(confidence: float, certainty: Certainty) -> str:
    if certainty == Certainty.UNDETERMINED:
        return "D"
    high, mid, low = GRADE_THRESHOLDS
    if confidence >= high:
        return "A"
    if confidence >= mid:
        return "B"
    if confidence >= low:
        return "C"
    return "D"


def _quality_card(findings: list[Finding], applicable_items: int) -> dict:
    """质量卡：分级分布、门控分布、平均置信度与审查率（assessed/applicable）。"""
    grades = {"A": 0, "B": 0, "C": 0, "D": 0}
    gate_reasons: dict[str, int] = {}
    confidences: list[float] = []
    assessed_items: set[str] = set()
    for finding in findings:
        grades[finding.grade] = grades.get(finding.grade, 0) + 1
        reason = finding.provenance.get("gate_reason", "direct")
        gate_reasons[reason] = gate_reasons.get(reason, 0) + 1
        if finding.certainty != Certainty.UNDETERMINED:
            confidences.append(finding.confidence)
            assessed_items.add(finding.checklist_item_id)
    assessed = len(assessed_items)
    applicable = max(applicable_items, assessed)
    return {
        "grades": grades,
        "gate_reasons": gate_reasons,
        "avg_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        "assessed_items": assessed,
        "applicable_items": applicable,
        "review_rate": round(assessed / applicable, 4) if applicable else 0.0,
    }


def _apply_gates(findings: list[Finding], applicable_items: int) -> tuple[list[Finding], dict]:
    """统一门控仲裁：读取各门控标记 → 定展示原因 → 量化置信度 → 分 A/B/C/D 档 → 汇总质量卡。"""
    scored: list[Finding] = []
    for finding in findings:
        confidence = _confidence_of(finding)
        reason = "not_evaluated" if finding.certainty == Certainty.UNDETERMINED else _gate_reason(_gate_flags(finding))
        scored.append(
            finding.model_copy(
                update={
                    "confidence": confidence,
                    "grade": _grade_of(confidence, finding.certainty),
                    "provenance": {**finding.provenance, "gate_reason": reason},
                }
            )
        )
    return scored, _quality_card(scored, applicable_items)


def _mark_unassessed(findings: list[Finding], items: list[ReviewItem]) -> list[Finding]:
    """未被任何结论覆盖的清单条目显式登记为「本项未能判定」，替代此前的静默不出现。"""
    covered = {finding.checklist_item_id for finding in findings}
    extras = [undetermined_finding(item.id, item.title) for item in items if item.id not in covered]
    return findings + extras


def _normalize_item_id(raw_id: str, items: list[ReviewItem]) -> str:
    ids = {item.id for item in items}
    if raw_id in ids:
        return raw_id
    for item in items:
        if item.title == raw_id:
            return item.id
    return "unknown"


def _prompt_document_text(document: DocumentIR) -> str:
    """拼给模型的正文：段落 + 表体行。

    P2-2 后表格已移出 `paragraphs`，规则引擎与引用核验都消费表体；模型侧必须一并带上，
    否则「表内要素已纳入审查」的口径对模型不成立。
    """
    body = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        body.extend(" | ".join(cell for cell in row if cell) for row in table.rows if any(cell for cell in row))
    return limit_prompt_text("\n".join(body))


def _parse_llm_result(result, items: list[ReviewItem]) -> tuple[list[Finding], int]:
    """解析一次模型输出为结论列表；不符合契约的条目丢弃并计数。"""
    raw = json.loads(result.content)
    if isinstance(raw, dict):
        raw = raw.get("findings", [])

    findings: list[Finding] = []
    invalid = 0
    for entry in raw if isinstance(raw, list) else []:
        try:
            payload = LLMFindingPayload(**entry)
        except (ValidationError, TypeError):
            invalid += 1
            continue
        verdict = VERDICT_MAP[payload.verdict]
        severity = SEVERITY_MAP.get(payload.severity or "mid", Severity.MID)
        findings.append(
            Finding(
                finding_id=new_id("F"),
                checklist_item_id=_normalize_item_id(payload.checklist_item_id, items),
                verdict=verdict,
                severity=severity,
                headline=payload.headline[:200],
                description=payload.description[:2000],
                suggestion=payload.suggestion[:1000],
                provenance={"engine": "llm", "model": result.model, "prompt_version": "v1"},
            )
        )
    return findings, invalid


def _element_hints(items: list[ReviewItem], elements: list[Element]) -> dict[str, str]:
    """每条清单所需要素的原文线索（要素 value 为其所在句片段），用于提升定向检索命中率。"""
    required = _required_types(items)
    by_type: dict[str, list[Element]] = {}
    for element in elements:
        by_type.setdefault(element.type, []).append(element)
    hints: dict[str, str] = {}
    for item in items:
        values: list[str] = []
        for element_type in required.get(item.id, []):
            for element in by_type.get(element_type, [])[:2]:
                if isinstance(element.value, str):
                    values.append(element.value)
        hints[item.id] = " ".join(values)
    return hints


def _review_messages(
    document: DocumentIR,
    items: list[ReviewItem],
    elements: list[Element],
    settings,
    vision_facts: list[str] | None,
) -> list[dict]:
    """构造审查请求：定向模式每条只带相关原文片段，否则退回全文模式。"""
    if settings.llm_directed_review:
        index = build_index(document)
        context = directed_context(items, index, _element_hints(items, elements))
        return build_directed_review_prompt(items, context, vision_facts)
    return build_review_prompt(items, _prompt_document_text(document))


def _dual_check(
    findings: list[Finding], provider: LLMProvider, messages: list[dict], items: list[ReviewItem]
) -> tuple[list[Finding], dict]:
    """双模型互证：同题再跑一次，逐条比对 verdict；分歧条目降为存疑并记录。"""
    try:
        second = provider.complete_structured(messages, temperature=0.3)
    except LLMUnavailable:
        return findings, {}
    second_findings, _ = _parse_llm_result(second, items)
    verdicts = {finding.checklist_item_id: finding.verdict for finding in second_findings}
    adjusted: list[Finding] = []
    for finding in findings:
        other = verdicts.get(finding.checklist_item_id)
        if other is not None and other != finding.verdict:
            adjusted.append(
                finding.model_copy(
                    update={
                        "verdict": Verdict.UNCERTAIN,
                        "provenance": {**finding.provenance, "dual_check": "disagree", "dual_verdict": other.value},
                    }
                )
            )
        else:
            adjusted.append(finding)
    usage = {
        "input": second.tokens.get("input", 0),
        "output": second.tokens.get("output", 0),
        "retries": second.retries,
    }
    return adjusted, usage


def _llm_findings(
    document: DocumentIR,
    items: list[ReviewItem],
    provider: LLMProvider,
    elements: list[Element],
    settings,
    vision_facts: list[str] | None = None,
) -> tuple[list[Finding], dict, int]:
    messages = _review_messages(document, items, elements, settings, vision_facts)
    result = provider.complete_structured(messages)
    findings, invalid = _parse_llm_result(result, items)
    usage = {
        "input": result.tokens.get("input", 0),
        "output": result.tokens.get("output", 0),
        "retries": result.retries,
    }
    if settings.llm_dual_check:
        findings, extra = _dual_check(findings, provider, messages, items)
        usage["input"] += extra.get("input", 0)
        usage["output"] += extra.get("output", 0)
    return findings, usage, invalid


def review_document(
    document: DocumentIR,
    items: list[ReviewItem],
    provider: LLMProvider | None = None,
    use_llm: bool = False,
    demote_on_figures: bool | None = None,
    media_root: str | Path | None = None,
) -> ReviewReport:
    started = time.monotonic()
    settings = get_settings()
    paper_type, type_evidence = classify(document)
    items_for_review = (
        [item for item in items if item.id in REVIEW_ALLOWED_ITEMS] if paper_type == "review" else items
    )
    notes: list[str] = []
    # 条目级判定主体分工（judge 字段为唯一事实源）：结构/数值类由规则侧判定，不进提示词。
    rule_tier_items = [item for item in items_for_review if item.judge == "rule"]
    llm_tier_items = [item for item in items_for_review if item.judge != "rule"]
    if paper_type == "review":
        skipped = len(items) - len(items_for_review)
        notes.append(
            f"识别为综述/理论论文（非实证）：已跳过 {skipped} 条实证类检查（如数据划分/基线/消融/统计检验/可复现性）。"
        )
    elements = extract_elements(document)
    # 严重度以清单配置（severity_default）为唯一事实源，规则内部的硬编码仅作缺省。
    severity_defaults = {item.id: item.severity_default for item in items}
    rule_findings = run_rules(document, elements, severity_defaults)
    if paper_type == "review":
        rule_findings = [f for f in rule_findings if f.checklist_item_id in REVIEW_ALLOWED_ITEMS]
    tokens = {"input": 0, "output": 0, "retries": 0}
    llm_findings: list[Finding] = []

    # 视觉识读先于模型审查：把图内数值作为结构化事实注入定向提示词（多模态入证）。
    vision_findings: list[Finding] = []
    vision_facts: list[str] = []
    vision_read = False
    if use_llm and provider is not None and settings.llm_vision_enabled and document.images:
        vision_findings, vision_tokens = read_figure_values(
            document, provider, media_root, max_images=settings.llm_vision_max_images
        )
        vision_read = bool(vision_findings)
        vision_facts = [
            f"第 {finding.provenance.get('image_index', 0) + 1} 张图：" + "、".join(finding.provenance.get("vision_values", []))
            for finding in vision_findings
            if finding.provenance.get("vision_values")
        ]
        tokens["input"] += vision_tokens.get("input", 0)
        tokens["output"] += vision_tokens.get("output", 0)

    if use_llm:
        if provider is None:
            notes.append("未配置模型服务，已降级为规则引擎结果（FR-D5）。")
        else:
            try:
                llm_findings, usage, invalid = _llm_findings(
                    document, llm_tier_items, provider, elements, settings, vision_facts
                )
                tokens["input"] += usage["input"]
                tokens["output"] += usage["output"]
                tokens["retries"] = usage["retries"]
                notes.append(
                    f"已按条目判定主体分流：{len(rule_tier_items)} 条结构/数值类由规则侧判定（不送模型），"
                    f"{len(llm_tier_items)} 条语义类送模型判定。"
                )
                if settings.llm_directed_review:
                    notes.append("已启用按要素定向送审：每条清单只携带其相关原文片段与判定准则。")
                if settings.llm_dual_check:
                    notes.append("已启用双模型互证：同题两次判定，分歧条目降级为存疑。")
                if vision_facts:
                    notes.append(f"已把 {len(vision_facts)} 张图的图内数值作为结构化事实注入模型审查。")
                if invalid:
                    notes.append(f"模型输出中有 {invalid} 条不符合契约，已丢弃。")
            except LLMUnavailable as exc:
                safe_logger().warning("llm_unavailable: %s", exc)
                notes.append("模型判定暂不可用，已降级为规则引擎结果（FR-D5）。")

    merged = _merge_findings(rule_findings, llm_findings)
    if provider is not None and use_llm:
        merged = verify_findings(document, merged, provider, max_items=settings.llm_verify_max_items)
    findings = _attach_evidence(merged, items_for_review, elements, _rule_anchors(rule_findings))
    findings = _apply_judge_tiers(findings, items_for_review, settings.llm_advisory_only)
    findings = _mark_unassessed(findings, items_for_review)
    unassessed = [finding for finding in findings if finding.certainty == Certainty.UNDETERMINED]
    if unassessed:
        notes.append(
            f"共 {len(unassessed)} 条清单项因未检出触发要素而未能判定（报告中标记为「本项未能判定」，不计入问题数）。"
        )
    # 审查报告不再承载「修改后示范」：该字段已由 CompareFinding.revision_status 取代，
    # 具体补写文本只在生成修改稿时使用（app/engine/revision.py）。
    # R-DATA-*：数值自洽检测器族（清单外附加检查，确定性核验，不计入 17 条清单名额）。
    # 与规则结论同一口径：数据划分属实证类内容，综述/理论论文跳过该组检查，避免实证检查噪声。
    numeric_findings = [] if paper_type == "review" else check_numeric_consistency(document)
    if numeric_findings:
        findings.extend(numeric_findings)
        notes.append(
            f"数值自洽检测（R-DATA-*）检出 {len(numeric_findings)} 处数值不一致（确定性核验，清单外附加检查）。"
        )
    findings.extend(check_figure_consistency(document))

    if vision_findings:
        findings.extend(vision_findings)
        notes.append(
            f"已识读 {len(vision_findings)} 张插图并回填图内数值线索（列为「存疑」，需人工复核）。"
        )

    # 图像侧口径：规则判定不消费图内数据；若视觉识读已产出线索则据此表述，避免说法与实现不符
    image_note = (
        "图内数值已由视觉识读产出「存疑」线索，规则判定仍不消费图内数据"
        if vision_read
        else "图像内部数据未参与规则判定"
    )
    figure_references = find_figure_references(document)
    demote = settings.demote_on_figures if demote_on_figures is None else demote_on_figures
    if figure_references:
        suffix = "（已启用保守模式：可能依赖图表的条目降级为存疑）" if demote else ""
        if document.tables:
            notes.append(
                f"检测到 {len(figure_references)} 处图表引用（图/表）：其中 {len(document.tables)} 个表格已完成结构化解析，"
                f"表内要素已纳入审查；{image_note}，若统计量仅出现在图像中，相关条目可能漏报或误报。{suffix}"
            )
        else:
            notes.append(
                f"检测到 {len(figure_references)} 处图表引用（图/表）：{image_note}，"
                f"若统计量仅出现在图表中，相关条目可能漏报或误报。{suffix}"
            )
        if demote:
            findings = demote_for_figures(findings, document=document, elements=elements)

    # 统一门控仲裁 + 输出质量量化：在所有门控（证据门/判定档/图表降级/引用核验/图识读）落标之后，
    # 由唯一入口读取标记、定展示原因、算置信度、分 A/B/C/D 档并汇总质量卡。
    findings, quality = _apply_gates(findings, len(items_for_review))

    duration_ms = int((time.monotonic() - started) * 1000)
    report = ReviewReport(
        report_id=new_id("rep"),
        document_name=document.source_name,
        checklist_version=",".join(sorted({item.version for item in items})) or "-",
        findings=findings,
        counts=_counts(findings),
        duration_ms=duration_ms,
        tokens=tokens,
        notes=notes,
        paper_type=paper_type,
        figure_references=len(figure_references),
        demote_on_figures=demote,
        quality=quality,
    )
    safe_logger().info(
        "review_done report_id=%s problems=%s assessed=%s tokens_in=%s tokens_out=%s duration_ms=%s",
        report.report_id,
        report.counts.get("total", 0),
        report.counts.get("assessed", 0),
        tokens.get("input", 0),
        tokens.get("output", 0),
        duration_ms,
    )
    return report
