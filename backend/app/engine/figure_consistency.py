"""L1 图-文一致性审查：题注提取、引用-题注对账、题注与正文样本量核对（P2-1 / 需求 15.5.1）。

覆盖需求列出的三类判定：① 图/表缺少题注；② 正文引用了某图/表但无对应题注；
③ 题注声明的样本量与引用该图/表的正文段矛盾。全部只用纯文本，不依赖图内数据
（图内数据识读属 P2-3）；仅在文档确实含图片或表格时才判定，避免对「论文节选」样本误报。
结论作为清单外的附加检查条目 `R-FIG-01` 输出，不占用 17 条清单名额。
"""
import re

from app.core.ids import new_id
from app.models.schemas import Anchor, DocumentIR, Finding, Paragraph, Severity, Verdict

ITEM_ID = "R-FIG-01"

CAPTION = re.compile(
    r"^\s*(?P<kind>Supplementary\s+(?:Fig(?:ure)?|Table)|附图|附表|Fig\.?|Figure|Table|图|表)"
    r"\s*(?P<number>\d+|[一二三四五六七八九十]+)(?P<rest>.*)$",
    re.IGNORECASE,
)
REFERENCE = re.compile(
    r"(?P<kind>Supplementary\s+(?:Fig(?:ure)?|Table)|附图|附表|Fig\.?|Figure|Table|图|表)"
    r"\s*(?P<number>\d+|[一二三四五六七八九十]+)",
    re.IGNORECASE,
)
# 题注编号后必须紧跟分隔符或行尾，避免把「表2报告了…」这类正文句误判为题注
CAPTION_SEPARATOR = re.compile(r"^\s*$|^[\s：:．.、,，\-—()（）\[\]]")
# 题注/正文中的样本量声明：n=42 / 42 例 / 14 名
SAMPLE_SIZE = re.compile(r"(?:[nN]\s*=\s*(\d[\d,]*)|(\d[\d,]*)\s*(例|名|个|张|幅|台|只|人))")
# 这些量词视为同一量纲「计数」，使「n=42」与「42 例」可直接比数值
_COUNT_UNITS = {"例", "名", "个", "只", "人"}
_ZH_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _zh_to_int(text: str) -> int | None:
    if text.isdigit():
        return int(text)
    if text == "十":
        return 10
    if len(text) == 2:
        if text[0] == "十" and text[1] in _ZH_DIGITS:
            return 10 + _ZH_DIGITS[text[1]]
        if text[1] == "十" and text[0] in _ZH_DIGITS:
            return _ZH_DIGITS[text[0]] * 10
    if len(text) == 3 and text[1] == "十" and text[0] in _ZH_DIGITS and text[2] in _ZH_DIGITS:
        return _ZH_DIGITS[text[0]] * 10 + _ZH_DIGITS[text[2]]
    return _ZH_DIGITS.get(text)


def _key_of(kind: str, number: str) -> tuple[str, int] | None:
    """归一为标准键 ("图"|"表", 编号)；中文数字与阿拉伯数字统一。"""
    lowered = kind.lower()
    if lowered.startswith("supplementary"):
        bucket = "表" if "table" in lowered else "图"
    elif "fig" in lowered or "图" in kind:
        bucket = "图"
    else:
        bucket = "表"
    value = _zh_to_int(number)
    return None if value is None else (bucket, value)


def _label(key: tuple[str, int]) -> str:
    return f"{key[0]}{key[1]}"


def _samples_in(text: str) -> dict[str, int]:
    """文本中的样本量声明 → {量纲: 数值}；n=42 与「42 例」量纲一致，可直接比数值。"""
    found: dict[str, int] = {}
    for match in SAMPLE_SIZE.finditer(text):
        unit = "计数" if match.group(1) or match.group(3) in _COUNT_UNITS else str(match.group(3))
        found.setdefault(unit, int((match.group(1) or match.group(2)).replace(",", "")))
    return found


def find_captions(document: DocumentIR) -> dict[tuple[str, int], int]:
    """题注段落 → {编号: 段落 index}；编号后无分隔符的正文句不计入。"""
    captions: dict[tuple[str, int], int] = {}
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        match = CAPTION.match(text)
        if not match or not CAPTION_SEPARATOR.match(match.group("rest")):
            continue
        key = _key_of(match.group("kind"), match.group("number"))
        if key is not None:
            captions.setdefault(key, paragraph.index)
    return captions


def find_references(document: DocumentIR, caption_indexes: set[int]) -> dict[tuple[str, int], list[int]]:
    """正文引用 → {编号: 出现段落 index 列表}；题注段落自身不计为引用。"""
    references: dict[tuple[str, int], list[int]] = {}
    for paragraph in document.paragraphs:
        if paragraph.index in caption_indexes:
            continue
        for match in REFERENCE.finditer(paragraph.text):
            key = _key_of(match.group("kind"), match.group("number"))
            if key is not None:
                references.setdefault(key, []).append(paragraph.index)
    return references


def _problem(headline: str, description: str, suggestion: str, anchor_index: int, check: str) -> Finding:
    return Finding(
        finding_id=new_id("F"),
        checklist_item_id=ITEM_ID,
        verdict=Verdict.PROBLEM,
        severity=Severity.LOW,
        headline=headline,
        description=description,
        anchors=[Anchor(paragraph_index=anchor_index)],
        suggestion=suggestion,
        provenance={"engine": "rule", "rule_id": ITEM_ID, "figure_check": check},
    )


def check_figure_consistency(document: DocumentIR) -> list[Finding]:
    """① 缺题注 ② 引用无对应题注 ③ 题注/正文样本量矛盾；纯节选（无图表）不判定。"""
    captions = find_captions(document)
    image_count = int(document.meta.get("image_count") or 0)
    table_count = len(document.tables)
    if image_count == 0 and table_count == 0:
        return []

    by_index = {paragraph.index: paragraph for paragraph in document.paragraphs}
    references = find_references(document, set(captions.values()))
    findings: list[Finding] = []

    for bucket, seen_count in (("图", image_count), ("表", table_count)):
        if seen_count and not any(key[0] == bucket for key in captions):
            findings.append(
                _problem(
                    f"文档含 {seen_count} 个{'图片' if bucket == '图' else '表格'}，但未识别到{'图题' if bucket == '图' else '表题'}",
                    f"解析到 {seen_count} 个{'内嵌图片' if bucket == '图' else '表格'}，但全文未检出"
                    f"「{bucket}1」形式的题注（也可能题注版式未被识别），无法核对{'图' if bucket == '图' else '表'}与正文的对应关系。",
                    f"为每{'张图' if bucket == '图' else '个表'}补充规范化题注（如「{_label((bucket, 1))} 名称」），并在正文中引用。",
                    max(by_index, default=0),
                    "caption_missing",
                )
            )

    for key, indexes in sorted(references.items()):
        if key in captions:
            continue
        if (image_count if key[0] == "图" else table_count) == 0:
            continue
        findings.append(
            _problem(
                f"正文引用了 {_label(key)}，但未找到对应题注",
                f"正文第 {indexes[0]} 段引用了「{_label(key)}」，但全文未检出同编号的题注，"
                "可能缺少图/表或题注编号不一致。",
                f"核对{_label(key)}是否存在，并补齐题注或统一编号。",
                indexes[0],
                "reference_without_caption",
            )
        )

    findings.extend(_check_sample_size(captions, references, by_index))
    return findings


def _check_sample_size(
    captions: dict[tuple[str, int], int],
    references: dict[tuple[str, int], list[int]],
    by_index: dict[int, Paragraph],
) -> list[Finding]:
    """题注声明的样本量与引用该图表的正文段不一致时报出（同为纯文本，不做图内识读）。"""
    findings: list[Finding] = []
    for key, caption_index in sorted(captions.items()):
        caption = by_index.get(caption_index)
        if caption is None:
            continue
        captioned = _samples_in(caption.text)
        if not captioned:
            continue
        for index in references.get(key, []):
            paragraph = by_index.get(index)
            if paragraph is None:
                continue
            for unit, value in _samples_in(paragraph.text).items():
                other = captioned.get(unit)
                if other is None or other == value:
                    continue
                findings.append(
                    _problem(
                        f"{_label(key)} 题注与正文的样本量不一致",
                        f"题注声明 {other}{unit}，而引用该图表的正文第 {index} 段声明 {value}{unit}，"
                        "两处口径不一致，需核对题注或正文数值。",
                        f"核对{_label(key)}对应的样本量，统一题注与正文的表述。",
                        index,
                        "sample_size_conflict",
                    )
                )
    return findings
