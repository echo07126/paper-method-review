"""清理提交材料中的内部元信息：引用块（> ...）、内部文档指路、版本后缀等。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAT = ROOT / "materials"


def strip_blockquotes(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))


def drop_section(text: str, heading: str) -> str:
    """删除指定 ### 小节（从标题到下一个同级/更高级标题）。"""
    lines = text.splitlines()
    out, skipping = [], False
    for line in lines:
        if line.strip() == heading:
            skipping = True
            continue
        if skipping and line.startswith("### "):
            skipping = False
        if skipping:
            continue
        out.append(line)
    return "\n".join(out)


files = [
    MAT / "00-材料总览.md",
    MAT / "01-软件说明文档.md",
    MAT / "02-核心算法说明.md",
    MAT / "03-测试报告.md",
    MAT / "04-技术栈运行环境与部署.md",
    MAT / "05-功能演示视频" / "视频脚本与要求.md",
]
for path in files:
    text = path.read_text(encoding="utf-8")
    text = strip_blockquotes(text)
    text = text.replace("# 论文方法论审查助手 · 软件说明文档（v2，按赛题大纲组织）", "# 论文方法论审查助手 · 软件说明文档")
    if path.name == "01-软件说明文档.md":
        text = drop_section(text, "### 4.1 开发流程与分工")
        text = text.replace(
            "- 详细清单：`docs/安全与运维核查清单.md`（25 项，全部已实现）。",
            "- 25 项安全控制点全部已实现（上传校验、越权防护、限流、密钥服务端化、日志脱敏、生产配置守卫、非 root 容器、CI 依赖扫描）。",
        )
        text = text.replace(
            "- **工具链**：`pytest`（38 项）、`smoke.py` / `api_check.py` / `live_check.py`（HTTP 链路）、`eval_ac.py`（评测）、`security_audit.py`（安全核查）、`sync_check.py`（接口/文档一致性）、前端 `vue-tsc`。\n", "")
    if path.name == "05-视频脚本与要求.md" or path.name == "视频脚本与要求.md":
        if "成品命名为" not in text:
            text = text.replace("- 时长 3–5 分钟；1080p；画面清晰；关键操作配字幕；讲解与操作同步。",
                                "- 成品命名为 `演示视频.mp4` 并放入本目录。\n- 时长 3–5 分钟；1080p；画面清晰；关键操作配字幕；讲解与操作同步。")
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    print(f"cleaned: {path.name}")
