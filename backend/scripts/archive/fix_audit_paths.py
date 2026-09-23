"""修正核查脚本：页数上限的取证位置改为 validators/files。"""
from pathlib import Path

path = Path(__file__).resolve().parent / "security_audit.py"
text = path.read_text(encoding="utf-8")
old = 'check("上传：页数上限生效", "max_pages 是否被使用", "max_pages" in read(APP / "api" / "routes_upload.py"))'
new = 'check("上传：页数上限生效", "validators/files 使用 max_pages", "max_pages" in read(APP / "validators.py") and "max_pages" in read(APP / "storage" / "files.py"))'
if old in text:
    path.write_text(text.replace(old, new), encoding="utf-8")
    print("核查脚本已修正")
else:
    print("[warn] 未找到页数检查锚点")
