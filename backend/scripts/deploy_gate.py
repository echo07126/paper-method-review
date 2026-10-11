"""交付门禁：核对《交付核查清单（本地 Docker 包）》，仅「⬜ 需运行方完成」计入阻塞。

三态语义（见 docs/operations/生产上线待办清单.md）：
- `✅ 已内置` / `✅ 已完成` → 就绪，不阻塞；
- `➖ 不适用（不上公网）` → 本地交付形态下无需执行，不阻塞；
- `⬜ 需运行方完成` → 阻塞，逐项列出并返回非零。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def configure_stdio() -> None:
    """让中文待办在 Windows、重定向输出和 CI 中均保持 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


ROOT = Path(__file__).resolve().parents[2]
CHECKLIST = ROOT / "docs" / "operations" / "生产上线待办清单.md"
# 表格列：# | 待办 | 状态 | 说明（状态列三态前缀：✅ / ⬜ / ➖）
ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(✅[^|]*|⬜[^|]*|➖[^|]*)\s*\|\s*(.*?)\s*\|\s*$",
    re.MULTILINE,
)
PENDING = "⬜"
BUILT = "✅"
NOT_APPLICABLE = "➖"


def main() -> int:
    configure_stdio()

    if not CHECKLIST.exists():
        print(f"交付门禁错误：未找到核查清单 {CHECKLIST}", file=sys.stderr)
        return 2

    text = CHECKLIST.read_text(encoding="utf-8")
    rows = ROW_RE.findall(text)
    if not rows:
        print("交付门禁错误：未从清单中解析到核查项，请检查表格格式。", file=sys.stderr)
        return 2

    pending = [(number, title) for number, title, status, _ in rows if status.strip().startswith(PENDING)]
    built = sum(1 for _, _, status, _ in rows if status.strip().startswith(BUILT))
    not_applicable = sum(1 for _, _, status, _ in rows if status.strip().startswith(NOT_APPLICABLE))
    ready = len(rows) - len(pending)

    print("本地交付核查门禁（不上公网）")
    print(f"清单：{CHECKLIST.relative_to(ROOT)}")
    print(f"进度：{ready}/{len(rows)} 就绪（{built} 已内置 + {not_applicable} 不适用），{len(pending)}/{len(rows)} 待办")
    print()

    if not pending:
        print("通过：本清单全部就绪（已内置 / 已完成 / 不适用），可交付。")
        return 0

    print(f"阻塞：以下 {len(pending)} 项需运行方完成")
    for number, title in pending:
        print(f"  [{number}/{len(rows)}] {title}")

    print()
    print("处理：完成一项后，将清单中的“⬜ 需运行方完成”改为“✅ 已完成”，再运行本脚本。")
    print("结论：门禁未通过，尚不可交付。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())