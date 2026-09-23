from pathlib import Path

path = Path(__file__).resolve().parent / "security_audit.py"
text = path.read_text(encoding="utf-8")
old = 'check("容器：非 root 运行", "Dockerfile USER", bool(grep_files(FE, r"^USER ")) or bool(grep_files(ROOT / "backend", r"^USER ")))'
new = 'check("容器：非 root 运行", "Dockerfile USER 指令", bool(grep_files(FE, r"USER\\s+[a-z]")) and bool(grep_files(ROOT / "backend", r"USER\\s+[a-z]")))'
if old in text:
    path.write_text(text.replace(old, new), encoding="utf-8")
    print("已修正容器检查")
else:
    print("[warn] 未找到容器检查锚点")
