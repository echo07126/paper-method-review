"""证据检索（RAG）：把原文切成可检索片段，供「按要素定向送审」与「证据检索式审查」使用。

设计要点
--------
- **零外部依赖**：不引入向量库；中文按 bigram、ASCII 按词切分，做集合重叠打分，
  结果稳定可解释（同一输入必得同一排序），便于测试与回归。
- **片段带锚点**：片段来源为正文段落与表体行，均保留 `paragraph_index`，
  模型给出的结论可回溯到原文位置，避免「无证据结论」。
- **支撑与反证**：`search` 取相关片段作支撑；`search_counter` 额外筛出含否定/缺失
  信号的片段作反证，使结论「先检索证据再下判」。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.schemas import DocumentIR, ReviewItem

_ASCII_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_\-.]{1,}")
_HAN = re.compile(r"[^\u4e00-\u9fff]+")

# 反证信号：出现这些词说明「本该有某要素但文中以否定/缺失方式表述」，用于检索反证片段。
COUNTER_SIGNAL = re.compile(
    r"(未|没有|尚未|未能|缺乏|缺少|忽略|不曾|无法|不提供|不公开|仅|只|一次性)",
    re.IGNORECASE,
)


@dataclass
class Chunk:
    """可检索片段：正文段落或表体行，均带段落锚点。"""

    text: str
    paragraph_index: int
    kind: str  # paragraph | table
    tokens: tuple[str, ...] = field(default_factory=tuple)


def _tokens(text: str) -> tuple[str, ...]:
    """切分检索词：ASCII 小写词 + 中文 bigram（单字中文也保留）。"""
    tokens = [word.lower() for word in _ASCII_WORD.findall(text)]
    han = _HAN.sub("", text)
    if len(han) == 1:
        tokens.append(han)
    else:
        tokens.extend(han[i : i + 2] for i in range(len(han) - 1))
    return tuple(tokens)


def build_index(document: DocumentIR) -> list[Chunk]:
    """建立检索索引：跳过标题段，纳入正文段落与表体行。"""
    chunks: list[Chunk] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text or paragraph.is_heading:
            continue
        chunks.append(Chunk(text=text, paragraph_index=paragraph.index, kind="paragraph", tokens=_tokens(text)))
    for table in document.tables:
        for row in table.rows:
            text = " | ".join(cell for cell in row if cell)
            if text.strip():
                chunks.append(Chunk(text=text, paragraph_index=table.anchor.paragraph_index, kind="table", tokens=_tokens(text)))
    return chunks


def _score(query_tokens: set[str], chunk: Chunk) -> float:
    if not chunk.tokens:
        return 0.0
    overlap = len(query_tokens & set(chunk.tokens))
    if overlap <= 0:
        return 0.0
    # 归一化到查询词数：长片段不因词多而占优，短而相关的片段也能命中。
    return overlap / (len(query_tokens) ** 0.5)


def search(index: list[Chunk], query: str, top_k: int = 4, min_overlap: int = 1) -> list[Chunk]:
    """按查询词重叠检索相关片段；排序稳定（分数降序，其次段落序号升序）。"""
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return []
    scored: list[tuple[float, int, int, Chunk]] = []
    for position, chunk in enumerate(index):
        overlap = len(query_tokens & set(chunk.tokens))
        if overlap < min_overlap:
            continue
        scored.append((_score(query_tokens, chunk), chunk.paragraph_index, position, chunk))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [chunk for _, _, _, chunk in scored[:top_k]]


def search_counter(index: list[Chunk], query: str, top_k: int = 2) -> list[Chunk]:
    """检索「反证」片段：与查询相关且含否定/缺失信号的行（如「未报告」「仅一次」）。"""
    candidates = search(index, query, top_k=len(index) if index else 0)
    return [chunk for chunk in candidates if COUNTER_SIGNAL.search(chunk.text)][:top_k]


def _query_of(item: ReviewItem, element_hint: str = "") -> str:
    """条目检索词：标题 + 判定准则 +（可选）该条所需要素的原文线索。"""
    return " ".join(part for part in (item.title, item.description, element_hint) if part)


def directed_context(
    items: list[ReviewItem],
    index: list[Chunk],
    element_hint_of: dict[str, str] | None = None,
    top_k: int = 4,
    counter_k: int = 2,
) -> dict[str, dict[str, list[Chunk]]]:
    """为每个清单条目组装「相关原文片段」与「反证片段」。"""
    hints = element_hint_of or {}
    context: dict[str, dict[str, list[Chunk]]] = {}
    for item in items:
        query = _query_of(item, hints.get(item.id, ""))
        context[item.id] = {
            "support": search(index, query, top_k=top_k),
            "counter": search_counter(index, query, top_k=counter_k),
        }
    return context