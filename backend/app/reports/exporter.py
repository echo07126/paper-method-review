from typing import Protocol

from app.models.schemas import Certainty, ReviewReport

SEVERITY_LABEL = {"high": "严重", "mid": "中等", "low": "轻微"}
CERTAINTY_LABEL = {"deterministic": "确定性", "suspected": "疑似", "undetermined": "未判定"}
GRADE_LABEL = {"A": "高置信", "B": "中置信", "C": "低置信", "D": "待确认"}


class Exporter(Protocol):
    def render(self, report: ReviewReport) -> str: ...


class MarkdownExporter:
    name = "markdown"

    def render(self, report: ReviewReport) -> str:
        lines = [
            f"# 方法学审查报告 · {report.document_name}",
            "",
            f"- 报告 ID：{report.report_id}",
            f"- 清单版本：{report.checklist_version}",
            f"- 问题统计：严重 {report.counts.get('high', 0)} / 中等 {report.counts.get('mid', 0)} / 轻微 {report.counts.get('low', 0)}（共 {report.counts.get('total', 0)}）",
            f"- 确定性统计：确定性 {report.counts.get('deterministic', 0)} / 疑似 {report.counts.get('suspected', 0)} / 未判定 {report.counts.get('undetermined', 0)}",
            f"- 审查耗时：{report.duration_ms} ms",
            "",
        ]
        quality = report.quality or {}
        grades = quality.get("grades") or {}
        if quality:
            lines.extend(
                [
                    "## 输出质量卡",
                    f"- 分级分布：A 高置信 {grades.get('A', 0)} / B 中置信 {grades.get('B', 0)} / "
                    f"C 低置信 {grades.get('C', 0)} / D 待确认 {grades.get('D', 0)}",
                    f"- 平均置信度：{quality.get('avg_confidence', 0.0)}（0–1，越高越可采信）",
                    f"- 审查率：{quality.get('assessed_items', 0)}/{quality.get('applicable_items', 0)}"
                    f" = {quality.get('review_rate', 0.0):.0%}（已评估条目 / 适用条目）",
                    "",
                ]
            )
            gate_reasons = quality.get("gate_reasons") or {}
            if gate_reasons:
                lines.append("- 门控分布：" + "、".join(f"{key} {value}" for key, value in gate_reasons.items()))
                lines.append("")
        assessed = [f for f in report.findings if f.certainty != Certainty.UNDETERMINED]
        for finding in assessed:
            anchor = finding.anchors[0] if finding.anchors else None
            location = f"段落 {anchor.paragraph_index}" if anchor else "位置未定"
            severity = SEVERITY_LABEL.get(finding.severity.value, finding.severity.value)
            certainty = CERTAINTY_LABEL.get(finding.certainty.value, finding.certainty.value)
            grade = GRADE_LABEL.get(finding.grade, finding.grade)
            lines.append(f"## [{severity}·{certainty}·{finding.grade} {grade}] {finding.headline}")
            lines.append(f"- 清单条目：{finding.checklist_item_id}")
            lines.append(f"- 原文定位：{location}")
            lines.append(f"- 置信度：{finding.confidence}（{grade}）")
            if finding.description:
                lines.append(f"- 说明：{finding.description}")
            if finding.suggestion:
                lines.append(f"- 建议：{finding.suggestion}")
            lines.append("")
        uncertain = [finding for finding in report.findings if finding.verdict.value == "uncertain"]
        if uncertain:
            lines.append("## 存疑（需人工复核）")
            for finding in uncertain:
                lines.append(f"- [{finding.checklist_item_id}] {finding.headline}：{finding.description}")
            lines.append("")
        undetermined = [finding for finding in report.findings if finding.certainty == Certainty.UNDETERMINED]
        if undetermined:
            lines.append("## 本项未能判定（证据不足，不计入问题数）")
            for finding in undetermined:
                lines.append(f"- [{finding.checklist_item_id}] {finding.description}")
            lines.append("")
        if report.notes:
            lines.append("## 备注")
            lines.extend(f"- {note}" for note in report.notes)
        return "\n".join(lines)
