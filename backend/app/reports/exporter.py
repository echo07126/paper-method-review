from typing import Protocol

from app.models.schemas import ReviewReport

SEVERITY_LABEL = {"high": "严重", "mid": "中等", "low": "轻微"}


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
            f"- 审查耗时：{report.duration_ms} ms",
            "",
        ]
        for finding in report.findings:
            anchor = finding.anchors[0] if finding.anchors else None
            location = f"段落 {anchor.paragraph_index}" if anchor else "位置未定"
            lines.append(f"## [{SEVERITY_LABEL.get(finding.severity.value, finding.severity.value)}] {finding.headline}")
            lines.append(f"- 清单条目：{finding.checklist_item_id}")
            lines.append(f"- 原文定位：{location}")
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
        if report.notes:
            lines.append("## 备注")
            lines.extend(f"- {note}" for note in report.notes)
        return "\n".join(lines)
