"""把生产上线门禁挂到部署任务（T-19）并更新文档索引。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 1) 开发规范 T-19 增加门禁要求
dev = ROOT / "docs" / "开发规范与开发顺序.md"
text = dev.read_text(encoding="utf-8")
old = "| T-19 | 部署：Docker 镜像 + compose + 安全清单逐项通过 | T-07 | 17.5/G-05 | 本地与云端均可一键起；清单全绿 |"
new = "| T-19 | 部署：Docker 镜像 + compose + 安全清单逐项通过；**部署完成后必须执行《生产上线待办清单》8 项，未完成不得对外公开** | T-07 | 17.5/G-05 | 本地与云端均可一键起；`python backend/scripts/deploy_gate.py` 返回 0 |"
if old in text:
    text = text.replace(old, new)
else:
    print("[warn] 未找到 T-19 行")
if "deploy_gate.py" not in text:
    text = text.rstrip() + "\n\n### 部署门禁（强制）\n- 部署脚本/流水线最后一步必须运行 `python backend/scripts/deploy_gate.py`：若《生产上线待办清单》仍有未完成项，返回非零并阻止对外发布。\n- 清单：`docs/生产上线待办清单.md`（TLS/HSTS、安全组、生产 Key 轮换、备份与删除传播、日志轮转、监控告警、事件演练、镜像扫描）。\n"
dev.write_text(text, encoding="utf-8")
print("开发规范已挂载部署门禁")

# 2) 安全与运维核查清单 §3 标注状态并链接新文档
sec = ROOT / "docs" / "安全与运维核查清单.md"
text = sec.read_text(encoding="utf-8")
anchor = "## 3. 上线前必须人工完成（环境类，无法在代码内自动验证）"
if anchor in text and "生产上线待办清单" not in text:
    text = text.replace(
        anchor,
        anchor + "\n\n> **当前状态：8 项全部未完成（0/8）**，逐项操作步骤与验收标准见 `docs/生产上线待办清单.md`；部署完成后运行 `python backend/scripts/deploy_gate.py` 提醒执行。\n",
    )
    text = text.replace("| 1 | TLS 证书 + 强制 HTTPS 跳转 + 开启 HSTS |", "| 1 | ⬜ TLS 证书 + 强制 HTTPS 跳转 + 开启 HSTS |")
    text = text.replace("| 2 | 安全组/防火墙最小开放 |", "| 2 | ⬜ 安全组/防火墙最小开放 |")
    text = text.replace("| 3 | 生产独立密钥 + 轮换 |", "| 3 | ⬜ 生产独立密钥 + 轮换 |")
    text = text.replace("| 4 | 备份与删除传播 |", "| 4 | ⬜ 备份与删除传播 |")
    text = text.replace("| 5 | 日志轮转与保留 ≤30 天 |", "| 5 | ⬜ 日志轮转与保留 ≤30 天 |")
    text = text.replace("| 6 | 监控告警 |", "| 6 | ⬜ 监控告警 |")
    text = text.replace("| 7 | 事件响应演练 |", "| 7 | ⬜ 事件响应演练 |")
    text = text.replace("| 8 | 镜像漏洞扫描 |", "| 8 | ⬜ 镜像漏洞扫描 |")
    sec.write_text(text, encoding="utf-8")
    print("安全清单已标注未完成状态")

# 3) README 索引
readme = ROOT / "README.md"
text = readme.read_text(encoding="utf-8")
line = "- 生产上线待办（部署完成后执行，当前 0/8）→ docs/生产上线待办清单.md；门禁脚本 `backend/scripts/deploy_gate.py`"
if "生产上线待办清单" not in text:
    text = text.rstrip() + "\n" + line + "\n"
    readme.write_text(text, encoding="utf-8")
    print("README 已索引生产待办清单")
