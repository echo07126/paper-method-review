"""高级应用六项：按要素定向送审、RAG 检索、双模型互证、R-DATA-* 数值自洽、多模态入证。"""
import base64
import json
from pathlib import Path

from docx import Document
from docx.shared import Inches

from app.core.config import Settings, set_settings_override
from app.engine.checklist import load_checklist
from app.engine.llm_provider import LLMResult
from app.engine.numeric_consistency import check_numeric_consistency
from app.engine.prompts import build_directed_review_prompt
from app.engine.retrieval import build_index, directed_context, search, search_counter
from app.engine.reviewer import (
    _apply_gates,
    _confidence_of,
    _gate_flags,
    _gate_reason,
    _grade_of,
    review_document,
)
from app.engine.rules import DETERMINISTIC_RULES
from app.models.schemas import Anchor, Certainty, DocumentIR, Finding, Paragraph, ReviewItem, Severity, Verdict
from app.parsers.registry import parse_document

ROOT = Path(__file__).resolve().parents[2]
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


def _doc(paragraphs: list[str]) -> DocumentIR:
    return DocumentIR(
        source_name="t.docx",
        parser="docx",
        parser_version="1.3",
        paragraphs=[Paragraph(index=index, text=text) for index, text in enumerate(paragraphs)],
    )


# ---------------------------------------------------------------- RAG 检索

def test_index_and_search_hits_relevant_paragraph() -> None:
    document = _doc([
        "本文提出多尺度卷积模型，用于眼底图像分类。",
        "数据按 7:1:2 划分训练、验证与独立测试集，随机种子固定为 42。",
        "研究局限在于单中心回顾性数据。",
    ])
    hits = search(build_index(document), "数据划分 随机种子", top_k=1)
    assert hits and hits[0].paragraph_index == 1, "检索应命中划分与种子所在段落"


def test_counter_evidence_search_finds_negation() -> None:
    document = _doc([
        "本模型实验仅运行一次，未报告方差与置信区间。",
        "模型在测试集上的准确率达到 0.95。",
    ])
    counter = search_counter(build_index(document), "重复实验 方差 置信区间", top_k=2)
    assert any("未报告" in chunk.text for chunk in counter), "反证检索应取含否定表述的片段"


def test_directed_context_is_per_item() -> None:
    document = _doc([
        "数据按 7:1:2 划分训练、验证与独立测试集。",
        "本文提出注意力模块，但未做消融。",
    ])
    items = [
        ReviewItem(id="R-03", category="数据划分", title="训练/验证/测试集划分与信息泄漏防控", description="需明确划分方式与随机种子。"),
        ReviewItem(id="R-05", category="消融实验", title="关键模块消融实验", description="对声称有贡献的模块做有/无对照。"),
    ]
    context = directed_context(items, build_index(document))
    r03_texts = " ".join(chunk.text for chunk in context["R-03"]["support"])
    assert "划分" in r03_texts and "消融" not in r03_texts, "每条目只应带各自相关片段"


def test_directed_prompt_contains_description_and_vision_facts() -> None:
    items = [ReviewItem(id="R-06", category="评价指标", title="评价指标与任务匹配", description="指标应与任务目标一致。")]
    messages = build_directed_review_prompt(
        items, {"R-06": {"support": [], "counter": []}}, vision_facts=["第 1 张图：准确率 0.91"]
    )
    user = messages[1]["content"]
    assert "判定准则：指标应与任务目标一致" in user, "定向提示词必须携带该条判定准则"
    assert "图内数值线索" in user and "0.91" in user, "图内数值应作为结构化事实注入"


# -------------------------------------------------------- R-DATA-* 数值自洽

def test_ratio_sum_inconsistency_detected() -> None:
    findings = check_numeric_consistency(_doc(["数据按 7:1:5 划分训练、验证与测试集。"]))
    assert [f.checklist_item_id for f in findings] == ["R-DATA-01"]
    assert findings[0].certainty.value == "deterministic", "数值对账结论应为确定性核验"


def test_valid_ratio_is_not_flagged() -> None:
    assert check_numeric_consistency(_doc(["数据按 7:1:2 划分训练、验证与测试集。"])) == []
    assert check_numeric_consistency(_doc(["按 70:15:15 划分训练、验证与测试集。"])) == []


def test_percent_sum_inconsistency_detected() -> None:
    findings = check_numeric_consistency(_doc(["按 70%、20%、5% 划分训练、验证与测试集。"]))
    assert any(f.checklist_item_id == "R-DATA-02" for f in findings)


def test_multi_part_ratio_is_not_flagged() -> None:
    """≥4 段划分（如 5:2:2:1）须整体求和，不得只取前 3 段误判为不一致。"""
    assert check_numeric_consistency(_doc(["数据按 5:2:2:1 划分训练、验证、测试与外部测试集。"])) == []


def test_metric_percentage_not_counted_as_split_share() -> None:
    """同段落的指标百分比（如「准确率为 95%」）不应并入划分百分比合计。"""
    assert check_numeric_consistency(_doc(["数据按 70%、15%、15% 划分，模型准确率为 95%。"])) == []


def test_ci_out_of_range_detected_and_valid_not_flagged() -> None:
    bad = check_numeric_consistency(_doc(["准确率为 0.95（95% CI 0.80–0.90）。"]))
    assert any(f.checklist_item_id == "R-DATA-03" for f in bad)
    assert check_numeric_consistency(_doc(["准确率为 0.85（95% CI 0.80–0.90）。"])) == []


def test_numeric_findings_excluded_from_checklist_denominator(tmp_path: Path) -> None:
    """R-DATA-* 为清单外附加检查，item id 不在清单 17 条内，故不计入 AC-2/AC-3 分母。"""
    source = tmp_path / "data.docx"
    doc = Document()
    doc.add_heading("3. 结果", level=1)
    doc.add_paragraph("数据按 7:1:5 划分训练、验证与测试集。")
    doc.save(source)
    document = parse_document(source, source.name, None)
    items = load_checklist(ROOT / "checklists" / "quant-ai-v1.json")
    report = review_document(document, items)
    checklist_ids = {item.id for item in items}
    assert any(f.checklist_item_id == "R-DATA-01" for f in report.findings)
    assert "R-DATA-01" not in checklist_ids, "R-DATA-* 不应占用清单名额"


# ------------------------------------------------------------ 双模型互证

class _FlipProvider:
    """首次判定 problem、二次判定 pass，用于验证分歧降级。"""

    def __init__(self) -> None:
        self.review_calls = 0

    def complete_structured(self, messages, temperature: float = 0.0):
        if "逐字引用" in messages[0]["content"]:
            return LLMResult(content=json.dumps({"results": []}), model="flip", tokens={"input": 1, "output": 1}, retries=0, duration_ms=1)
        self.review_calls += 1
        verdict = "problem" if self.review_calls == 1 else "pass"
        content = json.dumps([
            {"checklist_item_id": "R-15", "verdict": verdict, "severity": "low", "headline": "h", "description": "d", "suggestion": "s"}
        ])
        return LLMResult(content=content, model="flip", tokens={"input": 1, "output": 1}, retries=0, duration_ms=1)


def test_dual_check_downgrades_disagreement(tmp_path: Path) -> None:
    set_settings_override(Settings(llm_dual_check=True, llm_advisory_only=False, llm_directed_review=True))
    try:
        source = tmp_path / "dual.docx"
        doc = Document()
        doc.add_heading("3. 结果", level=1)
        doc.add_paragraph("模型在测试集上的准确率为 0.95。")
        doc.save(source)
        document = parse_document(source, source.name, None)
        items = load_checklist(ROOT / "checklists" / "quant-ai-v1.json")
        report = review_document(document, items, provider=_FlipProvider(), use_llm=True)
    finally:
        set_settings_override(None)

    r15 = [f for f in report.findings if f.checklist_item_id == "R-15" and f.provenance.get("engine") == "llm"]
    assert r15, "应保留模型结论"
    assert r15[0].provenance.get("dual_check") == "disagree"
    assert r15[0].verdict == Verdict.UNCERTAIN, "两次判定分歧应降级为存疑"


# ---------------------------------------------------------- 多模态读图入证

class _CaptureProvider:
    """识读图片返回数值；审查调用时记录消息以断言图内数值已注入提示词。"""

    def __init__(self) -> None:
        self.review_messages: list[dict] | None = None

    def complete_structured(self, messages, temperature: float = 0.0):
        if isinstance(messages[1]["content"], list):
            return LLMResult(content=json.dumps({"values": ["准确率 0.91"], "concern": None}), model="cap", tokens={"input": 1, "output": 1}, retries=0, duration_ms=1)
        self.review_messages = messages
        return LLMResult(content=json.dumps([]), model="cap", tokens={"input": 1, "output": 1}, retries=0, duration_ms=1)


def test_vision_values_are_injected_into_review_prompt(tmp_path: Path) -> None:
    png = tmp_path / "dot.png"
    png.write_bytes(PNG_1x1)
    source = tmp_path / "fig.docx"
    doc = Document()
    doc.add_heading("3. 结果", level=1)
    doc.add_paragraph("如图1所示，模型性能优于基线。")
    doc.add_picture(str(png), width=Inches(1))
    doc.add_paragraph("图1 模型准确率对比")
    doc.save(source)
    document = parse_document(source, source.name, None)
    items = load_checklist(ROOT / "checklists" / "quant-ai-v1.json")

    provider = _CaptureProvider()
    review_document(document, items, provider=provider, use_llm=True, demote_on_figures=False, media_root=tmp_path)

    assert provider.review_messages is not None, "应发生审查调用"
    user = provider.review_messages[1]["content"]
    assert "准确率 0.91" in user, "图内数值应作为结构化事实注入审查提示词"


# ------------------------------------------------ 条目级判定主体分工（judge）

def test_checklist_judge_tiers_are_declared_and_consistent() -> None:
    """judge 是条目级「审查拆分」的唯一事实源，必须与确定性核验集合一致。"""
    items = load_checklist(ROOT / "checklists" / "quant-ai-v1.json")
    assert all(item.judge in {"rule", "llm", "advisory"} for item in items), "每条必须声明 judge 档位"
    rule_ids = {item.id for item in items if item.judge == "rule"}
    assert rule_ids == DETERMINISTIC_RULES, "rule 档应等于结构/数值类（确定性核验）集合"
    advisory_ids = {item.id for item in items if item.judge == "advisory"}
    assert advisory_ids == {"R-05", "R-10", "R-11", "R-12"}, "advisory 档为图表依赖/偏软的 4 条"


class _TierProvider:
    """记录审查提示词，并对 advisory（R-05）与 llm（R-15）两档各给一条 problem。"""

    def __init__(self) -> None:
        self.review_messages: list[dict] | None = None

    def complete_structured(self, messages, temperature: float = 0.0):
        if "逐字引用" in messages[0]["content"]:
            return LLMResult(
                content=json.dumps({"results": []}), model="tier", tokens={"input": 1, "output": 1}, retries=0, duration_ms=1
            )
        self.review_messages = messages
        content = json.dumps([
            {"checklist_item_id": "R-05", "verdict": "problem", "severity": "mid",
             "headline": "h5", "description": "d5", "suggestion": "s5"},
            {"checklist_item_id": "R-15", "verdict": "problem", "severity": "low",
             "headline": "h15", "description": "d15", "suggestion": "s15"},
        ])
        return LLMResult(content=content, model="tier", tokens={"input": 1, "output": 1}, retries=0, duration_ms=1)


def _tier_document(tmp_path: Path) -> DocumentIR:
    """2 段短文：含消融与局限要素，但段落数 <4 使 R-15 规则不介入、无 novel_module 使 R-05 规则不介入。"""
    source = tmp_path / "tier.docx"
    doc = Document()
    doc.add_paragraph("消融实验采用有/无对照。")
    doc.add_paragraph("研究局限在于单中心回顾性数据。")
    doc.save(source)
    return parse_document(source, source.name, None)


def _run_tier_review(tmp_path: Path):
    items = load_checklist(ROOT / "checklists" / "quant-ai-v1.json")
    provider = _TierProvider()
    set_settings_override(Settings(llm_advisory_only=False, llm_directed_review=True))
    try:
        report = review_document(_tier_document(tmp_path), items, provider=provider, use_llm=True)
    finally:
        set_settings_override(None)
    return report, provider


def test_rule_tier_items_are_not_sent_to_llm(tmp_path: Path) -> None:
    _, provider = _run_tier_review(tmp_path)
    assert provider.review_messages is not None, "应发生审查调用"
    user = provider.review_messages[1]["content"]
    assert "### R-01 " in user, "语义类条目应进入定向提示词"
    assert "### R-REF-01" not in user and "### R-REF-02" not in user, "结构/数值类条目不应送模型"


def test_llm_tier_problem_kept_and_advisory_tier_demoted(tmp_path: Path) -> None:
    report, _ = _run_tier_review(tmp_path)
    llm_findings = {
        finding.checklist_item_id: finding
        for finding in report.findings
        if finding.provenance.get("engine") == "llm"
    }
    assert llm_findings["R-15"].verdict == Verdict.PROBLEM, "llm 档模型结论可作为正式问题（已挂要素锚点）"
    assert llm_findings["R-05"].verdict == Verdict.UNCERTAIN, "advisory 档模型结论只作建议"
    assert llm_findings["R-05"].provenance.get("advisory") is True
    assert any("判定主体分流" in note for note in report.notes)


# -------------------------------------- 统一门控仲裁 + 置信度打分 + A/B/C/D 分级

def _finding(**overrides) -> Finding:
    base = dict(
        finding_id="F1",
        checklist_item_id="R-01",
        verdict=Verdict.PROBLEM,
        severity=Severity.MID,
        headline="h",
        description="d",
        provenance={"engine": "rule", "rule_id": "R-01"},
    )
    base.update(overrides)
    return Finding(**base)


def test_deterministic_rule_finding_scores_grade_a() -> None:
    finding = _finding(certainty=Certainty.DETERMINISTIC, anchors=[Anchor(paragraph_index=1)])
    confidence = _confidence_of(finding)
    assert confidence == 1.0, "确定性核验 + 有锚点 + 无降级门控应为满分"
    assert _grade_of(confidence, finding.certainty) == "A"


def test_llm_finding_without_evidence_scores_grade_d() -> None:
    finding = _finding(provenance={"engine": "llm", "evidence_gate": "no_evidence"})
    confidence = _confidence_of(finding)
    assert confidence < 0.4, "模型结论无原文证据应为最低档"
    assert _grade_of(confidence, finding.certainty) == "D"


def test_undetermined_finding_is_grade_d() -> None:
    undetermined = _finding(certainty=Certainty.UNDETERMINED, provenance={"engine": "rule", "not_evaluated": True})
    assert _confidence_of(undetermined) == 0.0
    assert _grade_of(0.0, undetermined.certainty) == "D"


def test_gate_arbitration_prefers_highest_priority_reason() -> None:
    """一条结论同时命中多个门控时，展示原因取优先级最高者，因子取最保守者。"""
    finding = _finding(provenance={"engine": "llm", "evidence_gate": "no_evidence", "advisory": True})
    assert set(_gate_flags(finding)) == {"no_evidence", "advisory"}
    assert _gate_reason(_gate_flags(finding)) == "no_evidence", "no_evidence 优先级高于 advisory"


def test_apply_gates_scores_every_finding_and_builds_quality_card() -> None:
    findings = [
        _finding(finding_id="F1", certainty=Certainty.DETERMINISTIC, anchors=[Anchor(paragraph_index=1)]),
        _finding(finding_id="F2", checklist_item_id="R-05", provenance={"engine": "llm", "advisory": True}),
        _finding(
            finding_id="F3",
            checklist_item_id="R-15",
            verdict=Verdict.UNCERTAIN,
            certainty=Certainty.UNDETERMINED,
            provenance={"engine": "rule", "not_evaluated": True},
        ),
    ]
    scored, quality = _apply_gates(findings, applicable_items=5)
    assert all(0.0 <= item.confidence <= 1.0 for item in scored), "置信度应落在 0–1"
    assert all(item.grade == _grade_of(item.confidence, item.certainty) for item in scored), "分级应与置信度一致"
    assert sum(quality["grades"].values()) == len(scored), "分级分布应覆盖全部结论"
    assert quality["assessed_items"] == 2 and quality["applicable_items"] == 5
    assert quality["review_rate"] == round(2 / 5, 4)
    assert scored[0].provenance["gate_reason"] == "direct"
    assert scored[1].provenance["gate_reason"] == "advisory"


def test_report_quality_card_is_internally_consistent() -> None:
    """端到端：报告级质量卡的分布、审查率与逐条置信度/分级必须自洽。"""
    items = load_checklist(ROOT / "checklists" / "quant-ai-v1.json")
    report = review_document(_doc(["数据按 7:1:5 划分训练、验证与测试集。"]), items)
    quality = report.quality
    assert sum(quality["grades"].values()) == len(report.findings)
    assert quality["grades"]["A"] >= 1, "确定性数值对账应进入高置信档"
    assert all(item.grade == _grade_of(item.confidence, item.certainty) for item in report.findings)
    assert quality["applicable_items"] == len(items)
    assert quality["review_rate"] == round(quality["assessed_items"] / quality["applicable_items"], 4)