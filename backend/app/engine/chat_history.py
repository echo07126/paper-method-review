"""追问多轮上下文：截断策略与消息构造（需求 15.5.4）。

上限为「10 轮 / 20 条消息 + 历史总字符 8000（含 system 消息）」；超出时**截断而非压缩**：
保留 system 与最近 N 轮历史，从最早一轮开始整轮丢弃，当前提问始终保留。
"""
from app.engine.prompts import SYSTEM_GUARD

CHAT_SYSTEM_SUFFIX = (
    "你现在只回答用户针对「某一条已定位审查问题」的追问，不要扩展到全文其它问题。"
    "写作要求：只用中文；先给结论，再给依据，全篇不超过 200 字；"
    "语气专业、直接、中肯，指出该写法在方法学或论证上的失分点，不客套、不铺垫；"
    "必须给出可落地的改法：可以直接套用的句式，或需要补上的实验、数据与说明；"
    "上下文不足时明确指出缺什么，不得编造原文没有的信息。"
)


def build_system_message() -> dict:
    return {"role": "system", "content": SYSTEM_GUARD + CHAT_SYSTEM_SUFFIX}


def truncate_history(history: list[dict], max_turns: int, max_chars: int, system_chars: int = 0) -> tuple[list[dict], bool]:
    """按「轮数 + 字符数」双重上限截断历史，返回 (保留的历史, 是否发生截断)。

    - 一轮 = 一条 user + 一条 assistant；`max_turns` 轮即最多 `2 × max_turns` 条；
    - 字符预算含 system 消息（`system_chars`），从最近往前保留，超出时从最早整轮丢弃；
    - `max_turns <= 0` 视为不留历史；单条最新消息本身即超限时仍保留它，确保最新上下文不丢。
    """
    if max_turns <= 0:
        return [], bool(history)
    kept = history[-(max_turns * 2):] if history else []
    truncated = len(kept) < len(history)
    # 从末尾按 2 条一截时，若历史条数为奇数会以 assistant 开头；回退一条使对话以 user 起始
    if kept and kept[0].get("role") != "user":
        kept = kept[1:]
        truncated = True

    def total() -> int:
        return system_chars + sum(len(str(message.get("content", ""))) for message in kept)

    while kept and total() > max_chars:
        if len(kept) <= 1:
            # 单条最新消息本身即超限时仍保留，确保最新上下文不丢
            break
        kept = kept[2:]  # 整轮（user+assistant）丢弃，避免留下孤立消息
        truncated = True
    return kept, truncated


def build_chat_messages(
    history: list[dict],
    question: str,
    max_turns: int,
    max_chars: int,
) -> tuple[list[dict], bool]:
    """构造多轮追问消息：system + 截断后的历史 + 当前提问。"""
    system = build_system_message()
    kept, truncated = truncate_history(
        history, max_turns=max_turns, max_chars=max_chars, system_chars=len(system["content"])
    )
    return [system, *kept, {"role": "user", "content": question}], truncated
