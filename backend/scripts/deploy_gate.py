"""部署门禁：检查《生产上线待办清单》，未完成时逐项输出并返回非零。"""

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
ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(⬜ 未完成|✅ 已完成)\s*\|\s*$",
    re.MULTILINE,
)
PENDING = "⬜ 未完成"


def main() -> int:
    configure_stdio()

    if not CHECKLIST.exists():
        print(f"部署门禁错误：未找到待办清单 {CHECKLIST}", file=sys.stderr)
        return 2

    text = CHECKLIST.read_text(encoding="utf-8")
    rows = ROW_RE.findall(text)
    if not rows:
        print("部署门禁错误：未从清单中解析到待办项，请检查表格格式。", file=sys.stderr)
        return 2

    pending = [(number, title) for number, title, status in rows if status == PENDING]
    completed = len(rows) - len(pending)

    print("生产上线部署门禁")
    print(f"清单：{CHECKLIST.relative_to(ROOT)}")
    print(f"进度：{completed}/{len(rows)} 已完成，{len(pending)}/{len(rows)} 待办")
    print()

    if not pending:
        print("通过：全部上线待办已完成，可以对外公开服务。")
        return 0

    print(f"阻塞：以下 {len(pending)} 项尚未完成")
    for number, title in pending:
        print(f"  [{number}/{len(rows)}] {title}")

    print()
    print("处理：完成一项后，将清单中的“⬜ 未完成”改为“✅ 已完成”，再运行本脚本。")
    print("结论：门禁未通过，暂不可对外公开服务。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())