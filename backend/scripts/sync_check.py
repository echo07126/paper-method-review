"""一致性核查：后端实际路由 vs 前端调用 vs 文档记录；关键字段与指标口径核对。"""
import json
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def backend_paths() -> list[str]:
    try:
        spec = httpx.get("http://127.0.0.1:8000/openapi.json", timeout=10).json()
        return sorted(spec.get("paths", {}).keys())
    except Exception as exc:  # noqa: BLE001
        print("无法读取 OpenAPI：", exc)
        return []


def frontend_calls() -> set[str]:
    calls: set[str] = set()
    pattern = re.compile(r"client\.(?:get|post|put|delete)(?:<[^>]*>)?\(\s*[`\"']([^`\"']+)[`\"']")
    for path in (ROOT / "frontend" / "src").rglob("*.ts"):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            calls.add(match.group(1))
    for path in (ROOT / "frontend" / "src").rglob("*.vue"):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            calls.add(match.group(1))
    return calls


def normalize(call: str) -> str:
    call = call.split("?")[0]
    call = re.sub(r"\$\{[^}]+\}", "{id}", call)
    return call


def docs_mentions() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in (ROOT / "docs").rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for endpoint in re.findall(r"/api/v1/[a-zA-Z0-9_/\-{}]+", text):
            counts[endpoint] = counts.get(endpoint, 0) + 1
    return counts


def main() -> int:
    paths = backend_paths()
    calls = frontend_calls()
    print("=== 后端实际路由（OpenAPI）===")
    for path in paths:
        print("  ", path)

    print("\n=== 前端调用 ===")
    mismatched = []
    for call in sorted(calls):
        normalized = normalize(call)
        full = "/api/v1" + normalized if not normalized.startswith("/api") else normalized
        full = full.replace("/api/v1/api/v1", "/api/v1")
        ok = any(
            re.sub(r"\{[^}]+\}", "{id}", p.replace("/api/v1", ""))
            == re.sub(r"\{[^}]+\}", "{id}", full.replace("/api/v1", ""))
            for p in paths
        )
        print(f"  {'OK ' if ok else 'MISS'} {call}")
        if not ok:
            mismatched.append(call)

    print("\n=== 文档中记录的接口 ===")
    for endpoint, count in sorted(docs_mentions().items()):
        print(f"  {endpoint}  (出现 {count} 次)")

    print("\n=== 关键字段一致性 ===")
    report_fields = {"report_id", "findings", "counts", "duration_ms", "tokens", "notes", "figure_references", "demote_on_figures"}
    types_ts = (ROOT / "frontend" / "src" / "api" / "types.ts").read_text(encoding="utf-8")
    missing = [field for field in report_fields if field not in types_ts]
    print("  前端 ReviewReport 缺少字段：", missing or "无")
    review_req = (ROOT / "backend" / "app" / "api" / "routes_review.py").read_text(encoding="utf-8")
    for field in ("document_id", "use_llm", "demote_on_figures"):
        print(f"  后端 ReviewRequest.{field}:", "存在" if field in review_req else "缺失")

    print("\n=== 关键指标口径（文档）===")
    for name in ("软件需求说明.md", "开发规范与开发顺序.md", "01-软件说明文档.md"):
        candidates = list(ROOT.rglob(name))
        if not candidates:
            print(f"  [缺失] {name}")
            continue
        text = candidates[0].read_text(encoding="utf-8")
        print(f"  {name}: 规则17条={'17' in text} 夹具分组={'夹具' in text or 'fixtures' in text} 二期路线={'二期' in text}")

    print("\n结论：", "前端调用与后端路由全部匹配" if not mismatched else f"存在不匹配 {mismatched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
