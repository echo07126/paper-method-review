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
from app.engine.paper_type import REVIEW_ALLOWED_ITEMS, classify
from app.engine.prompts import build_review_prompt
from app.engine.rules import run_rules
from app.engine.verification import verify_findings
from app.engine.vision import read_figure_values
from app.models.schemas import (
    DocumentIR,
    Element,
    Finding,
    ReviewItem,
    ReviewReport,
    Severity,
    Verdict,
)

MAX_PROMPT_CHARS = 12000

VERDICT_MAP = {
    "pass": Verdict.PASS,
    "problem": Verdict.PROBLEM,
    "not_applicable": Verdict.NOT_APPLICABLE,
    "uncertain": Verdict.UNCERTAIN,
}
SEVERITY_MAP = {"high": Severity.HIGH, "mid": Severity.MID, "low": Severity.LOW}


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
    counts = {"high": 0, "mid": 0, "low": 0, "total": 0, "pass": 0, "not_applicable": 0, "uncertain": 0, "assessed": 0}
    for finding in findings:
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
    """同一清单条目只保留一条结论：规则结论为主，LLM 文本补充，冲突则记录。"""
    merged: dict[str, Finding] = {f.checklist_item_id: f for f in rule_findings}
    extras: list[Finding] = []
    for finding in llm_findings:
        base = merged.get(finding.checklist_item_id)
        if base is None or finding.checklist_item_id == "unknown":
            extras.append(finding)
            continue
        vetoed = base.verdict == Verdict.PASS and finding.verdict == Verdict.PROBLEM
        merged[finding.checklist_item_id] = base.model_copy(
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
    return list(merged.values()) + extras


def _apply_advisory_mode(findings: list[Finding], enabled: bool) -> list[Finding]:
    """顾问模式：模型结论一律降级为「建议/存疑」，只有规则引擎才输出 problem。"""
    if not enabled:
        return findings
    adjusted: list[Finding] = []
    for finding in findings:
        if finding.provenance.get("engine") == "llm" and finding.verdict == Verdict.PROBLEM:
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


def _normalize_item_id(raw_id: str, items: list[ReviewItem]) -> str:
    ids = {item.id for item in items}
    if raw_id in ids:
        return raw_id
    for item in items:
        if item.title == raw_id:
            return item.id
    return "unknown"


def _llm_findings(document: DocumentIR, items: list[ReviewItem], provider: LLMProvider) -> tuple[list[Finding], dict, int]:
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)[:MAX_PROMPT_CHARS]
    messages = build_review_prompt(items, text)
    result = provider.complete_structured(messages)
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
    usage = {
        "input": result.tokens.get("input", 0),
        "output": result.tokens.get("output", 0),
        "retries": result.retries,
    }
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
    if paper_type == "review":
        skipped = len(items) - len(items_for_review)
        notes.append(
            f"识别为综述/理论论文（非实证）：已跳过 {skipped} 条实证类检查（如数据划分/基线/消融/统计检验/可复现性）。"
        )
    elements = extract_elements(document)
    rule_findings = run_rules(document, elements)
    if paper_type == "review":
        rule_findings = [f for f in rule_findings if f.checklist_item_id in REVIEW_ALLOWED_ITEMS]
    tokens = {"input": 0, "output": 0, "retries": 0}
    llm_findings: list[Finding] = []

    if use_llm:
        if provider is None:
            notes.append("未配置模型服务，已降级为规则引擎结果（FR-D5）。")
        else:
            try:
                llm_findings, usage, invalid = _llm_findings(document, items_for_review, provider)
                tokens = usage
                if invalid:
                    notes.append(f"模型输出中有 {invalid} 条不符合契约，已丢弃。")
            except LLMUnavailable as exc:
                safe_logger().warning("llm_unavailable: %s", exc)
                notes.append("模型判定暂不可用，已降级为规则引擎结果（FR-D5）。")

    merged = _merge_findings(rule_findings, llm_findings)
    if provider is not None and use_llm:
        merged = verify_findings(document, merged, provider)
    findings = _attach_evidence(merged, items_for_review, elements, _rule_anchors(rule_findings))
    findings = _apply_advisory_mode(findings, settings.llm_advisory_only)
    findings.extend(check_figure_consistency(document))

    vision_read = False
    if use_llm and provider is not None and settings.llm_vision_enabled and document.images:
        vision_findings, vision_tokens = read_figure_values(
            document, provider, media_root, max_images=settings.llm_vision_max_images
        )
        findings.extend(vision_findings)
        vision_read = bool(vision_findings)
        tokens["input"] += vision_tokens.get("input", 0)
        tokens["output"] += vision_tokens.get("output", 0)
        if vision_findings:
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
