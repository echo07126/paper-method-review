"""对运行中的服务做真实 HTTP 端到端检查（不使用 TestClient）。"""
import io
import sys
import tempfile
from pathlib import Path

import httpx
from docx import Document

BASE = "http://127.0.0.1:8000/api/v1"


def build_docx() -> bytes:
    doc = Document()
    doc.add_heading("3. Results", level=1)
    doc.add_paragraph("Figure 1 shows the accuracy of 0.91; we compared with the baseline ResNet-50.")
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=60, follow_redirects=True) as client:
        health = client.get("/health")
        print("health:", health.status_code, health.json())

        content = build_docx()
        upload = client.post("/uploads", files={"file": ("live.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        upload.raise_for_status()
        document_id = upload.json()["document_id"]
        print("upload:", upload.status_code, "sections=", len(upload.json()["sections"]), "warnings=", upload.json()["warnings"])

        strict = client.post("/reviews", json={"document_id": document_id, "use_llm": False, "demote_on_figures": False}).json()
        conservative = client.post("/reviews", json={"document_id": document_id, "use_llm": False, "demote_on_figures": True}).json()
        print("strict      :", strict["counts"], "figures=", strict["figure_references"], "demote=", strict["demote_on_figures"])
        print("conservative:", conservative["counts"], "figures=", conservative["figure_references"], "demote=", conservative["demote_on_figures"])
        assert conservative["demote_on_figures"] is True
        assert conservative["counts"]["total"] < strict["counts"]["total"]

        reports = client.get("/reports").json()
        print("reports:", len(reports), "->", reports[0]["report_id"] if reports else "-")
        report = client.get(f"/reports/{reports[0]['report_id']}").json()
        print("report fields:", sorted(report.keys()))
        export = client.get(f"/reports/{reports[0]['report_id']}/export", params={"format": "markdown"})
        print("export:", export.status_code, "bytes=", len(export.text))
        chat = client.post(f"/reports/{reports[0]['report_id']}/chat", json={"question": "怎么改？"}).json()
        print("chat source:", chat.get("source"))
        compare = client.post("/compare", json={"before_report_id": reports[0]["report_id"], "after_report_id": reports[1]["report_id"] if len(reports) > 1 else reports[0]["report_id"]})
        print("compare:", compare.status_code, list(compare.json().keys()))
        purge = client.post("/sessions/purge")
        print("purge:", purge.status_code, purge.json())
    print("LIVE CHECK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
