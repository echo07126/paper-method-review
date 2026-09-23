"""在需求文档与 README 中建立安全/运维核查文档的索引。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

req = ROOT / "docs" / "软件需求说明.md"
text = req.read_text(encoding="utf-8")
anchor = "### 17.5 上线安全检查清单（部署前逐项打勾）"
note = anchor + "\n\n> 自动核查：`python backend/scripts/security_audit.py`（当前 25 项全部已实现）；完整核查表、刻意取舍与环境类待办见 `docs/安全与运维核查清单.md`。\n"
if anchor in text and "security_audit.py" not in text:
    req.write_text(text.replace(anchor, note), encoding="utf-8")
    print("需求文档已索引安全核查")

readme = ROOT / "README.md"
text = readme.read_text(encoding="utf-8")
lines = [
    "- 接口说明（与后端同步）→ docs/API接口说明.md（`python backend/scripts/gen_api_doc.py` 生成）",
    "- 安全与运维核查 → docs/安全与运维核查清单.md（`python backend/scripts/security_audit.py`，当前 25/25 已实现）",
]
for line in lines:
    if line.split("→")[0].strip("- ") not in text:
        text = text.rstrip() + "\n" + line + "\n"
readme.write_text(text, encoding="utf-8")
print("README 已索引")

dev = ROOT / "docs" / "开发规范与开发顺序.md"
text = dev.read_text(encoding="utf-8")
if "security_audit.py" not in text:
    text = text.rstrip() + "\n\n### 安全与运维核查（常态化）\n- 每次涉及数据流/存储/外部调用的改动后，运行 `python backend/scripts/security_audit.py`（25 项控制点取证）与 `python backend/scripts/sync_check.py`（接口/文档一致性）。\n- 上线前按 `docs/安全与运维核查清单.md` 第 3 节逐项完成环境类检查（TLS、密钥轮换、备份、监控、演练）。\n"
    dev.write_text(text, encoding="utf-8")
    print("开发规范已加入常态化核查说明")
