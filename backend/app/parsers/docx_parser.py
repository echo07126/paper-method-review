import re
from collections import Counter
from pathlib import Path

from docx import Document as load_docx
from docx.oxml.ns import qn
from docx.table import Table as DocxTable
from docx.text.run import Run

from app.core.ids import new_id
from app.models.schemas import (
    Anchor,
    CitationMarker,
    DocumentIR,
    ImageRef,
    Paragraph,
    ReferenceEntry,
    Section,
    Sentence,
    Table,
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
TABLE_CAPTION_PATTERN = re.compile(r"^\s*(表|附表|Table|Supplementary\s+Table)\s*\d+", re.IGNORECASE)
NUMERIC_CELL = re.compile(r"\d")
MATH_TAGS = frozenset({qn("m:oMath"), qn("m:oMathPara")})
MATH_TEXT_TAG = qn("m:t")
RUN_TAG = qn("w:r")
BLIP_TAG = qn("a:blip")
# VML 图片（旧式浮动图）不在 python-docx 的 nsmap 中，直接用限定名
IMAGEDATA_TAG = "{urn:schemas-microsoft-com:vml}imagedata"
EMBED_ATTR = qn("r:embed")
LINK_ATTR = qn("r:id")
CONTENT_TYPE_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/bmp": "bmp", "image/tiff": "tif", "image/webp": "webp"}


def _image_rel_ids(paragraph) -> list[str]:
    """段落内嵌/浮动图片的关系 ID（按文档流顺序；drawing 与 VML 两种形态都覆盖）。"""
    rel_ids: list[str] = []
    for node in paragraph._p.iter(BLIP_TAG, IMAGEDATA_TAG):
        rel_id = node.get(EMBED_ATTR) or node.get(LINK_ATTR)
        if rel_id:
            rel_ids.append(rel_id)
    return rel_ids


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


def _paragraph_chunks(paragraph) -> list[tuple[str, bool, Run | None]]:
    """按文档流顺序切分段落：普通 run 保留上标标记，OMML 公式转为纯文本块（run 为 None）。"""
    run_map = {run._r: run for run in paragraph.runs}
    chunks: list[tuple[str, bool, Run | None]] = []
    for child in paragraph._p:
        if child.tag == RUN_TAG:
            run = run_map.get(child)
            if run is not None:
                chunks.append((run.text, bool(run.font.superscript), run))
        elif child.tag in MATH_TAGS:
            text = "".join(node.text or "" for node in child.iter(MATH_TEXT_TAG))
            if text.strip():
                chunks.append((text, False, None))
    return chunks


def _detect_header_rows(rows: list[list[str | None]]) -> int:
    """保守策略：仅首行、且首行无数字时才认定为表头；否则 header_rows=0。"""
    if len(rows) < 2:
        return 0
    first = [cell for cell in rows[0] if cell]
    if not first:
        return 0
    if any(NUMERIC_CELL.search(cell) for cell in first):
        return 0
    return 1


def _build_table(table: DocxTable, index: int, caption: str, anchor_index: int) -> Table:
    """把 python-docx 表格转为二维网格；合并单元格以 None 占位，表头保守识别。"""
    rows: list[list[str | None]] = []
    previous_row: list = []
    for row in table.rows:
        current_row = list(row.cells)
        cells: list[str | None] = []
        previous_tc = None
        for column, cell in enumerate(current_row):
            merged = (previous_tc is not None and cell._tc is previous_tc) or (
                column < len(previous_row) and cell is previous_row[column]
            )
            cells.append(None if merged else " ".join(cell.text.split()))
            previous_tc = cell._tc
        rows.append(cells)
        previous_row = current_row
    n_cols = max((len(row) for row in rows), default=0)
    for row in rows:
        row.extend([None] * (n_cols - len(row)))
    return Table(
        id=new_id("tbl"),
        index=index,
        caption=caption,
        rows=rows,
        header_rows=_detect_header_rows(rows),
        n_rows=len(rows),
        n_cols=n_cols,
        anchor=Anchor(paragraph_index=anchor_index),
    )


def _image_caption(paragraphs: list[Paragraph], anchor_index: int) -> tuple[str, int | None]:
    """图片题注：图题通常紧邻图片下方（与表题在上方相反），故向后找 3 段。"""
    for paragraph in paragraphs:
        if anchor_index < paragraph.index <= anchor_index + 3 and CAPTION_PATTERN.match(paragraph.text.strip()):
            return paragraph.text.strip(), paragraph.index
    return "", None


def _save_images(document, path: Path, pending: list[tuple[str, int]], paragraphs: list[Paragraph]) -> list[ImageRef]:
    """把内嵌图片落盘到会话目录下的 `<docx名>_media/`，并返回带锚点的 ImageRef。

    落盘位置在会话临时目录内，因此 `purge_session_files()` 会随会话一并清除（无需额外删除链）。
    """
    if not pending:
        return []
    media_dir = path.parent / f"{path.stem}_media"
    images: list[ImageRef] = []
    for rel_id, anchor_index in pending:
        part = document.part.related_parts.get(rel_id)
        blob = getattr(part, "blob", b"") if part is not None else b""
        if not blob:
            continue
        media_type = (getattr(part, "content_type", "") or "").lower()
        filename = f"fig{len(images) + 1}.{CONTENT_TYPE_EXT.get(media_type, 'bin')}"
        media_dir.mkdir(parents=True, exist_ok=True)
        (media_dir / filename).write_bytes(blob)
        caption, caption_index = _image_caption(paragraphs, anchor_index)
        images.append(
            ImageRef(
                id=new_id("img"),
                index=len(images),
                media_type=media_type,
                byte_size=len(blob),
                filename=f"{media_dir.name}/{filename}",
                caption=caption,
                caption_index=caption_index,
                anchor=Anchor(paragraph_index=anchor_index),
            )
        )
    return images


class DocxParser:
    name = "docx"
    version = "1.3"
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
        tables: list[Table] = []
        sections: list[Section] = []
        sup_spans: list[tuple[int, str]] = []
        pending_images: list[tuple[str, int]] = []
        heuristic_headings = 0
        math_count = 0
        table_count = 0
        index = 0

        for block in document.iter_inner_content():
            if isinstance(block, DocxTable):
                table_count += 1
                caption = ""
                if paragraphs and TABLE_CAPTION_PATTERN.match(paragraphs[-1].text.strip()):
                    caption = paragraphs[-1].text.strip()
                tables.append(
                    _build_table(
                        block,
                        index=table_count - 1,
                        caption=caption,
                        anchor_index=paragraphs[-1].index if paragraphs else 0,
                    )
                )
                continue

            paragraph = block
            current = index
            index += 1
            # 图片锚点须在 `continue` 之前采集：纯图片段落（无文本）也会被跳过建段落
            pending_images.extend((rel_id, current) for rel_id in _image_rel_ids(paragraph))
            chunks = _paragraph_chunks(paragraph)
            math_count += sum(1 for _, _, run in chunks if run is None)
            text = "".join(part for part, _, _ in chunks)
            if not text.strip():
                continue
            style = paragraph.style.name or "Normal"
            style_heading = style == "Title" or style.startswith("Heading")
            run_objects = [run for _, _, run in chunks if run is not None]
            if style_heading:
                is_heading, level = True, _style_level(style)
            else:
                is_heading, level, _reason = _looks_like_heading(text, style, run_objects)
                if is_heading:
                    heuristic_headings += 1
                    if not style or style == "Normal":
                        style = "HeuristicHeading"
            paragraphs.append(
                Paragraph(index=current, text=text, style=style, is_heading=is_heading, sentences=split_sentences(text))
            )
            if is_heading:
                sections.append(
                    Section(id=new_id("sec"), title=text.strip(), level=level, paragraph_index=current, confidence=1.0 if style_heading else 0.7)
                )
            buffer = ""
            current_sup: list[str] = []
            for part, is_sup, _ in chunks:
                if is_sup:
                    current_sup.append(part)
                    continue
                if current_sup:
                    span = "".join(current_sup)
                    if is_citation_span(span, buffer[-1] if buffer else "", part[:1]):
                        sup_spans.append((current, span))
                    current_sup = []
                buffer += part
            if current_sup:
                span = "".join(current_sup)
                if is_citation_span(span, buffer[-1] if buffer else "", ""):
                    sup_spans.append((current, span))

        image_count = len(getattr(document, "inline_shapes", []))
        images = _save_images(document, path, pending_images, paragraphs)
        image_count = image_count or len(images)
        table_rows = sum(table.n_rows for table in tables)

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
            warnings.append(
                f"文档含 {image_count} 张内嵌图片（已落盘 {len(images)} 张供视觉识读）：图像内部数值不参与规则判定，"
                "若统计量仅标注在图内可能漏检。"
            )
        if table_count:
            warnings.append(f"检测到 {table_count} 个表格（{table_rows} 行），已做单元格结构解析并移出正文段落流。")
        if not references:
            warnings.append("未识别到参考文献列表，引用对账可能不完整。")

        return DocumentIR(
            source_name=path.name,
            parser=self.name,
            parser_version=self.version,
            sections=sections,
            paragraphs=paragraphs,
            tables=tables,
            images=images,
            citations=citations,
            references=list(references.values()),
            warnings=warnings,
            meta={
                "capabilities": self.capabilities.__dict__,
                "paragraph_count": len(paragraphs),
                "image_count": image_count,
                "image_saved": len(images),
                "table_count": table_count,
                "table_rows": table_rows,
                "math_count": math_count,
                "heuristic_headings": heuristic_headings,
            },
        )
