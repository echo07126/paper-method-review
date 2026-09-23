import re
from collections import Counter
from pathlib import Path

from docx import Document as load_docx

from app.core.ids import new_id
from app.models.schemas import (
    Anchor,
    CitationMarker,
    DocumentIR,
    Paragraph,
    ReferenceEntry,
    Section,
    Sentence,
)
from app.parsers.base import ParseError, ParserCapabilities

REFERENCE_TITLES = {"references", "bibliography", "参考文献", "文献", "references and notes"}
SENTENCE_SPLIT = re.compile(r"(?<=[。！？.!?])\s+")
BRACKET_TOKEN = re.compile(r"\[[^\[\]]+\]")
RANGE_OR_NUMBER = re.compile(r"\d+(?:\s*[-–—]\s*\d+)?")
REFERENCE_ITEM = re.compile(r"^\s*\[?(\d+)\]?[\.\、\．\:\)]?\s+")
CITATION_BRACKET = re.compile(r"^\[\s*[\d\s,，\-–—]+\s*\]$")
BARE_CITATION = re.compile(r"^\d{1,3}$")
MATH_PREV = set(")]}〉」】‖|·×+-=/")

SECTION_KEYWORDS = (
    "摘要", "abstract", "引言", "introduction", "背景", "background",
    "方法", "材料与方法", "materials and methods", "methods", "method", "methodology",
    "结果", "results", "讨论", "discussion", "结论", "conclusion", "conclusions",
    "局限性", "limitations", "相关工作", "related work", "实验", "experiments",
    "参考文献", "references", "文献综述",
)
NUMBERING_PATTERN = re.compile(r"^\s*(?:(\d+(?:\.\d+)*)[\.、\s]|([一二三四五六七八九十]+)[、.]|([IVXivx]+)\.\s)")
TERMINAL_PUNCTUATION = re.compile(r"[。！？.!?；;，,]\s*$")
HEURISTIC_MAX_LENGTH = 80
CAPTION_PATTERN = re.compile(r"^\s*(图|表|附图|附表|Fig\.?|Figure|Table)\s*\d+", re.IGNORECASE)


def is_citation_span(span: str, prev_char: str, next_char: str) -> bool:
    """仅把“引用样式”的上标当作角标，过滤 R²、O((d+1)³)、‖·‖² 等数学上标。"""
    span = span.strip()
    if not span:
        return False
    if CITATION_BRACKET.match(span):
        return True
    if BARE_CITATION.match(span):
        if prev_char and (prev_char.isalnum() or prev_char in MATH_PREV):
            return False
        if next_char and next_char in MATH_PREV + "%":
            return False
        return True
    return False


def split_sentences(text: str) -> list[Sentence]:
    sentences: list[Sentence] = []
    start = 0
    index = 0
    for match in SENTENCE_SPLIT.finditer(text):
        end = match.start()
        chunk = text[start:end].strip()
        if chunk:
            sentences.append(Sentence(index=index, text=chunk, char_start=start, char_end=end))
            index += 1
        start = match.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(Sentence(index=index, text=tail, char_start=start, char_end=len(text)))
    return sentences


def expand_numbers(token: str) -> list[int]:
    numbers: list[int] = []
    for part in RANGE_OR_NUMBER.findall(token):
        part = part.replace(" ", "")
        if re.search(r"[-–—]", part):
            left, right = re.split(r"[-–—]", part, maxsplit=1)
            if left.isdigit() and right.isdigit():
                numbers.extend(range(int(left), int(right) + 1))
        elif part.isdigit():
            numbers.append(int(part))
    return numbers


def _style_level(style_name: str) -> int:
    if style_name == "Title":
        return 0
    parts = style_name.split()
    if parts and parts[-1].isdigit():
        return int(parts[-1])
    return 1


def _numbering_level(text: str) -> int | None:
    match = NUMBERING_PATTERN.match(text)
    if not match:
        return None
    if match.group(1):
        return min(match.group(1).count(".") + 1, 4)
    return 1


def _looks_like_heading(text: str, style_name: str, runs) -> tuple[bool, int, str]:
    """样式缺失时的兜底判定：编号前缀 / 章节关键词 / 全加粗 / 字号偏大。"""
    stripped = text.strip()
    if not stripped or len(stripped) > HEURISTIC_MAX_LENGTH:
        return False, 1, ""
    if CAPTION_PATTERN.match(stripped):
        return False, 1, ""
    if TERMINAL_PUNCTUATION.search(stripped) and _numbering_level(stripped) is None:
        return False, 1, ""

    numbered = _numbering_level(stripped)
    keyword = any(stripped.lower().startswith(word) or stripped.lower() == word for word in SECTION_KEYWORDS)
    all_bold = bool(runs) and all(run.bold for run in runs if run.text.strip())
    bigger = False
    sizes = [run.font.size.pt for run in runs if run.font.size is not None and run.text.strip()]
    if sizes:
        body = _BODY_SIZE[0]
        if body and max(sizes) >= body * 1.15:
            bigger = True

    if numbered is not None or keyword or all_bold or bigger:
        level = numbered or 1
        reason = "numbering" if numbered is not None else ("keyword" if keyword else ("bold" if all_bold else "font-size"))
        return True, level, reason
    return False, 1, ""


_BODY_SIZE: list[float | None] = [None]


def _estimate_body_size(document) -> None:
    sizes: list[float] = []
    for paragraph in document.paragraphs:
        style = paragraph.style.name or ""
        if style == "Title" or style.startswith("Heading"):
            continue
        for run in paragraph.runs:
            if run.font.size is not None and run.text.strip():
                sizes.append(round(run.font.size.pt, 1))
    _BODY_SIZE[0] = Counter(sizes).most_common(1)[0][0] if sizes else None


class DocxParser:
    name = "docx"
    version = "1.1"
    capabilities = ParserCapabilities(pages=False, superscript=True, bbox=False, tables=True, ocr=False)

    def supports(self, filename: str, mime: str | None) -> bool:
        return filename.lower().endswith(".docx")

    def parse(self, path: Path) -> DocumentIR:
        try:
            document = load_docx(str(path))
        except Exception as exc:  # noqa: BLE001 - 统一转为解析错误
            raise ParseError("docx_parse_failed", f"DOCX 解析失败：{exc}") from exc

        _estimate_body_size(document)

        paragraphs: list[Paragraph] = []
        sections: list[Section] = []
        sup_spans: list[tuple[int, str]] = []
        heuristic_headings = 0

        for index, paragraph in enumerate(document.paragraphs):
            runs = [(run.text, bool(run.font.superscript), run) for run in paragraph.runs]
            text = "".join(part for part, _, _ in runs)
            if not text.strip():
                continue
            style = paragraph.style.name or "Normal"
            style_heading = style == "Title" or style.startswith("Heading")
            run_objects = [run for _, _, run in runs]
            if style_heading:
                is_heading, level = True, _style_level(style)
            else:
                is_heading, level, _reason = _looks_like_heading(text, style, run_objects)
                if is_heading:
                    heuristic_headings += 1
                    if not style or style == "Normal":
                        style = "HeuristicHeading"
            paragraphs.append(
                Paragraph(index=index, text=text, style=style, is_heading=is_heading, sentences=split_sentences(text))
            )
            if is_heading:
                sections.append(
                    Section(id=new_id("sec"), title=text.strip(), level=level, paragraph_index=index, confidence=1.0 if style_heading else 0.7)
                )
            buffer = ""
            current: list[str] = []
            for part, is_sup, _ in runs:
                if is_sup:
                    current.append(part)
                    continue
                if current:
                    span = "".join(current)
                    if is_citation_span(span, buffer[-1] if buffer else "", part[:1]):
                        sup_spans.append((index, span))
                    current = []
                buffer += part
            if current:
                span = "".join(current)
                if is_citation_span(span, buffer[-1] if buffer else "", ""):
                    sup_spans.append((index, span))

        image_count = len(getattr(document, "inline_shapes", []))
        table_count = 0
        table_rows = 0
        next_index = (max((p.index for p in paragraphs), default=-1) + 1) if paragraphs else 0
        for table in getattr(document, "tables", []):
            table_count += 1
            for row in table.rows:
                cells = [" ".join(cell.text.split()) for cell in row.cells]
                row_text = " | ".join(cell for cell in cells if cell)
                if not row_text:
                    continue
                paragraphs.append(
                    Paragraph(index=next_index, text=row_text, style="Table", is_heading=False, sentences=split_sentences(row_text))
                )
                table_rows += 1
                next_index += 1

        ref_start = len(paragraphs)
        for position, paragraph in enumerate(paragraphs):
            if paragraph.is_heading and paragraph.text.strip().lower() in REFERENCE_TITLES:
                ref_start = position
                break
        references: dict[int, ReferenceEntry] = {}
        for paragraph in paragraphs[ref_start + 1:]:
            match = REFERENCE_ITEM.match(paragraph.text)
            if match:
                number = int(match.group(1))
                references[number] = ReferenceEntry(
                    number=number, text=paragraph.text.strip(), anchor=Anchor(paragraph_index=paragraph.index)
                )

        citations: list[CitationMarker] = []
        for paragraph_index, span in sup_spans:
            tokens = BRACKET_TOKEN.findall(span) or [span]
            for token in tokens:
                numbers = expand_numbers(token)
                if not numbers:
                    continue
                citations.append(
                    CitationMarker(
                        text=token,
                        numbers=numbers,
                        anchor=Anchor(paragraph_index=paragraph_index),
                        unresolved=[n for n in numbers if n not in references],
                    )
                )

        warnings: list[str] = []
        if not sections:
            warnings.append("未识别到章节标题，请手动确认章节边界。")
        if heuristic_headings:
            warnings.append(f"有 {heuristic_headings} 个标题通过版式启发式识别（非 Word 样式），建议核对章节边界。")
        if image_count:
            warnings.append(f"文档含 {image_count} 张内嵌图片：图片/图表内容未解析，统计量若仅标注在图内可能漏检。")
        if table_count:
            warnings.append(f"检测到 {table_count} 个表格（{table_rows} 行），已按行文本纳入审查（未做单元格结构解析）。")
        if not references:
            warnings.append("未识别到参考文献列表，引用对账可能不完整。")

        return DocumentIR(
            source_name=path.name,
            parser=self.name,
            parser_version=self.version,
            sections=sections,
            paragraphs=paragraphs,
            citations=citations,
            references=list(references.values()),
            warnings=warnings,
            meta={
                "capabilities": self.capabilities.__dict__,
                "paragraph_count": len(paragraphs) - table_rows,
                "image_count": image_count,
                "table_count": table_count,
                "table_rows": table_rows,
                "heuristic_headings": heuristic_headings,
            },
        )
