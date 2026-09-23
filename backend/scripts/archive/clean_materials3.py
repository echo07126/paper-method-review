"""去掉标题后遗留的孤立 '---' 与多余空行。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
files = list((ROOT / "materials").glob("*.md")) + list((ROOT / "materials").glob("*/*.md"))
for path in files:
    text = path.read_text(encoding="utf-8")
    # 标题后紧跟（空行若干 + '---'）→ 只保留一个空行
    text = re.sub(r"^(# .+?)\n\s*\n---\n", r"\1\n\n", text, count=1, flags=re.MULTILINE)
    # 连续 3 个以上换行压成 2 个
    text = re.sub(r"\n{3,}", "\n\n", text)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
print("清理完成")
