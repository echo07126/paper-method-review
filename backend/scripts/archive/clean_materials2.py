"""二次清理：重排 4.x 编号；去掉材料中的内部文档路径引用。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAT = ROOT / "materials"
one = MAT / "01-软件说明文档.md"
text = one.read_text(encoding="utf-8")

# 1) 重排 4.x 编号（4.1 已删除）
for old, new in [
    ("### 4.2 关键代码片段", "### 4.1 关键代码片段"),
    ("### 4.3 AI 专项测试用例与结果", "### 4.2 AI 专项测试用例与结果"),
    ("### 4.4 部署方案", "### 4.3 部署方案"),
    ("### 4.5 技术栈与运行环境", "### 4.4 技术栈与运行环境"),
    ("### 4.6 安全与合规（要点）", "### 4.5 安全与合规（要点）"),
]:
    text = text.replace(old, new)

# 2) 去掉内部路径引用（保留事实描述）
text = text.replace(
    "- **生产上线前置**：`docs/生产上线待办清单.md` 8 项（TLS/HSTS、安全组、生产 Key 轮换、备份与删除传播、日志轮转 ≤30 天、监控告警、事件演练、镜像扫描），由 `deploy_gate.py` 门禁拦截。",
    "- **生产上线前置**：8 项环境类检查（TLS/HSTS、安全组、生产 Key 轮换、备份与删除传播、日志轮转 ≤30 天、监控告警、事件演练、镜像扫描），由发布门禁脚本自动拦截。",
)
old_appendix = """- 盲测报告 4 份：`docs/盲测报告-机器学习中的线性回归.md`、`docs/盲测报告-模型参数的确定方法.md`、`docs/盲测报告-中文短文本分类.md`、`docs/盲测报告-预埋缺陷实证论文.md`
- 接口与运维：`docs/API接口说明.md`、`docs/安全与运维核查清单.md`、`docs/生产上线待办清单.md`
- 需求与规范：`docs/软件需求说明.md`（v0.7）、`docs/开发规范与开发顺序.md`"""
new_appendix = """- 用户盲测报告 4 份（综述 2 篇、规范实证 1 篇、预埋缺陷实证 1 篇）
- 接口说明、安全与运维核查清单、生产上线待办清单
- 软件需求说明、开发规范与开发顺序"""
text = text.replace(old_appendix, new_appendix)
one.write_text(text, encoding="utf-8")

# 3) 04：去掉内部路径
four = MAT / "04-技术栈运行环境与部署.md"
t = four.read_text(encoding="utf-8")
t = t.replace(
    "| 上线前必做 | `docs/生产上线待办清单.md` 8 项（TLS/HSTS、安全组、生产 Key 轮换、备份与删除传播、日志轮转、监控告警、事件演练、镜像扫描），由 `deploy_gate.py` 门禁拦截 |",
    "| 上线前必做 | 8 项环境类检查（TLS/HSTS、安全组、生产 Key 轮换、备份与删除传播、日志轮转、监控告警、事件演练、镜像扫描），由发布门禁脚本自动拦截 |",
)
t = t.replace(
    "| 核查记录 | `docs/安全与运维核查清单.md`（25 项，全部已实现）+ `backend/scripts/security_audit.py` |",
    "| 核查记录 | 25 项安全控制点全部已实现，并提供自动核查脚本 `backend/scripts/security_audit.py` |",
)
four.write_text(t, encoding="utf-8")

# 4) 00：索引标题去掉括号
zero = MAT / "00-材料总览.md"
z = zero.read_text(encoding="utf-8").replace("## 2. 支撑文档索引（docs/）", "## 2. 支撑文档索引")
zero.write_text(z, encoding="utf-8")
print("二次清理完成")
