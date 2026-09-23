from pathlib import Path

path = Path(__file__).resolve().parents[2] / "backend" / "app" / "engine" / "rules.py"
lines = path.read_text(encoding="utf-8").splitlines()
cleaned = []
removed = 0
for line in lines:
    stripped = line.strip()
    if stripped.startswith('r"(测试集[^。；，]{0,12}(调参') or stripped.startswith("(调参|模型选择|超参数选择|网格搜索)[^。；，]{0,12}(基于"):
        removed += 1
        continue
    cleaned.append(line)
path.write_text("\n".join(cleaned) + "\n", encoding="utf-8")
print(f"清理残留行 {removed} 行")
