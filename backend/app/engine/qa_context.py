"""全文问答上下文（自由提问）：模型需读取全文并记忆，上下文上限与追问一致。

约束（沿用需求 15.5.4，内容不变，仅把作用域从「当前 finding」扩到「全文」）：
- 轮数上限 10 轮 / 20 条消息；字符上限 8000（含 system）；
- 全文按段落索引顺序拼装，超预算时按**整段**丢弃（不截半段），保留系统提示与最近对话；
- 论文文本一律包在 DATA 区块内，声明为待审数据、非指令（防注入）。
"""
from app.engine.prompts import SYSTEM_GUARD

QA_SYSTEM_SUFFIX = (
    "\n用户正在就这篇论文提问。请基于 DATA 区块中的全文内容回答，"
    "重点指出该文在方法学、实验设计、可复现性、写作与可扩展方向上的可优化点；"
    "不得编造文中没有的内容，若全文未提供相关信息请直接说明。"
)


def build_qa_system_message() -> dict:
    return {"role": "system", "content": SYSTEM_GUARD + QA_SYSTEM_SUFFIX}


def truncate_document_chunks(chunks: list[str], max_chars: int) -> tuple[list[str], bool]:
    """按**整段**边界把全文裁进字符预算（从后往前丢段，保证文档开头与系统提示保留）。

    返回 (保留的段落文本, 是否发生截断)。`max_chars <= 0` 视为不注入全文。
    """
    if max_chars <= 0:
        return [], bool(chunks)
    kept: list[str] = []
    used = 0
    for chunk in chunks:
        cost = len(chunk) + 1
        if used + cost > max_chars and kept:
            return kept, True
        if used + cost > max_chars:
            # 单段即超预算：保留该段，确保最新/首段上下文不丢
            return [chunk], True
        kept.append(chunk)
        used += cost
    return kept, False


def build_question_context(document_text: str, max_chars: int) -> str:
    """把全文注入提问上下文；超预算时按整段裁剪并给出显式提示。"""
    chunks = [line for line in document_text.splitlines() if line.strip()]
    kept, truncated = truncate_document_chunks(chunks, max_chars)
    body = "\n".join(kept)
    if truncated:
        body += "\n…（全文过长，已按段落边界省略部分内容；如需针对被省略部分提问，请缩小范围）"
    return body
