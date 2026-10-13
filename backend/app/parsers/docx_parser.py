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
# 参考文献章节标题在真实论文里常带章节编号/全角括号（「7 References」「6 参考文献」
# 「参考文献（References）」）。先剥掉编号前缀、括注与收尾标点再比对，否则整段引用对账
# 会因标题写法不同而整体失效（表现为全部引用「悬空」+ 误报「未识别到参考文献列表」）。
REFERENCE_HEADING_PREFIX = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*|[一二三四五六七八九十]+|[IVXivx]+)\s*[\.、．:：]?\s*"
)
REFERENCE_HEADING_TAIL = re.compile(r"[\s。．.:：、]+$")
REFERENCE_HEADING_INLINE = re.compile(r"[（(][^（()）]*[)）]")
# 中文断句：中文终止符（。！？；）后直接断句，无需空白；西文 .!? 仅在“非数字 + 后接空白 + 下一句以大写/CJK 起”时断句，
# 既修掉“中文段落永不切句”（原正则要求终止符后必须有空白），也避免把 “2. 方法”“0.912” 切成独立句。
SENTENCE_SPLIT = re.compile(r"(?<=[。！？；])|(?<![0-9][.?!])(?<=[.?!])\s+(?=[A-Z\u4e00-\u9fff“\"'(])")
BRACKET_TOKEN = re.compile(r"\[[^\[\]]+\]")
RANGE_OR_NUMBER = re.compile(r"\d+(?:\s*[-–—]\s*\d+)?")
# 参考文献条目编号，兼容三种常见写法（分组区分，取首个非空分组）：
#   [1]/［1］  括号式，编号后允许无空白（GB/T 7714、CNKI 导出风格「[1]张三…」）
#   1./1、/1)/1： 分隔符式
#   1 后接空白     裸编号式
REFERENCE_ITEM = re.compile(
    r"^\s*(?:[\[［]\s*(\d+)\s*[\]］]|(\d+)\s*[\.、．:：\)）]|(\d+)(?=\s))"
)
# 允许一个上标内并排多个方括号引用（「[1][2]」「[1-2][5]」），分隔符兼容中英文顿号/分号
CITATION_BRACKET = re.compile(r"^(?:\[\s*[\d\s,，、;；\-–—]+\s*\])+$")
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
        # 注意：MATH_PREV 是 set，不能与字符串相加（set + str 会抛 TypeError）
        if next_char and (next_char == "%" or next_char in MATH_PREV):
            return False
        return True
    return False


def _detect_language(text: str) -> str:
    """粗粒度语种判定：CJK 字符不少于拉丁字母即视为中文。

    该字段此前始终是默认值 "zh"（从未被赋值），下游若据它切换提示词/规则会一直走中文分支。
    这里给出一个可解释的判定：以「汉字数 ≥ 拉丁字母数」为中文，其余为英文；
    两种字符都不存在时按中文处理（本项目面向中文写作）。
    """
    han = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return "en" if latin > han else "zh"


def _reference_number(text: str) -> int | None:
    """从参考文献条目文本中取出编号；取首个非空分组（括号式 / 分隔符式 / 裸编号式）。"""
    match = REFERENCE_ITEM.match(text)
    if not match:
        return None
    for group in match.groups():
        if group:
            return int(group)
    return None


def _is_reference_heading(text: str) -> bool:
    """参考文献章节标题判定：容忍章节编号、全角括号括注与收尾标点。"""
    normalized = REFERENCE_HEADING_TAIL.sub("", REFERENCE_HEADING_PREFIX.sub("", text.strip()))
    if normalized.lower() in REFERENCE_TITLES:
        return True
    without_inline = REFERENCE_HEADING_TAIL.sub(
        "", REFERENCE_HEADING_INLINE.sub("", normalized).strip()
    )
    return without_inline.lower() in REFERENCE_TITLES


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


def _looks_like_heading(
    text: str, style_name: str, runs, body_size: float | None = None
) -> tuple[bool, int, str]:
    """样式缺失时的兜底判定：编号前缀 / 章节关键词 / 全加粗 / 字号偏大。

    `body_size` 由调用方显式传入而非读取模块级状态：解析在线程池中并发执行，
    模块级状态会让并发上传互相污染标题判定。
    """
    stripped = text.strip()
    if not stripped or len(stripped) > HEURISTIC_MAX_LENGTH:
        return False, 1, ""
    if CAPTION_PATTERN.match(stripped):
        return False, 1, ""
    if TERMINAL_PUNCTUATION.search(stripped) and _numbering_level(stripped) is None:
        return False, 1, ""

    numbered = _numbering_level(stripped)
    keyword = any(stripped.lower().startswith(word) or stripped.lower() == word for word in SECTION_KEYWORDS)
    # 只对「有文字」的 run 判定加粗：all() 作用于空序列恒为 True，
    # 会把「仅含制表符 + 公式」的段落误判为标题。
    text_runs = [run for run in runs if run.text.strip()]
    all_bold = bool(text_runs) and all(run.bold for run in text_runs)
    bigger = False
    sizes = [run.font.size.pt for run in runs if run.font.size is not None and run.text.strip()]
    if sizes and body_size:
        if max(sizes) >= body_size * 1.15:
            bigger = True

    if numbered is not None or keyword or all_bold or bigger:
        level = numbered or 1
        reason = "numbering" if numbered is not None else ("keyword" if keyword else ("bold" if all_bold else "font-size"))
        return True, level, reason
    return False, 1, ""


def _estimate_body_size(document) -> float | None:
    """正文字号估计（众数）。返回而非写入模块级状态，见 `_looks_like_heading` 的说明。"""
    sizes: list[float] = []
    for paragraph in document.paragraphs:
        style = paragraph.style.name or ""
        if style == "Title" or style.startswith("Heading"):
            continue
        for run in paragraph.runs:
            if run.font.size is not None and run.text.strip():
                sizes.append(round(run.font.size.pt, 1))
    return Counter(sizes).most_common(1)[0][0] if sizes else None


# 正文流包装元素：内部的 run 同属正文，必须递归展开，否则其文本整段丢失
# （`Paragraph.text` 是包含超链接文本的，直接遍历 `w:p` 子节点会漏掉 `w:hyperlink`）。
FLOW_CONTAINER_TAGS = frozenset(
    {qn("w:hyperlink"), qn("w:ins"), qn("w:smartTag"), qn("w:sdt"), qn("w:sdtContent")}
)


def _iter_flow(container, parent):
    """按文档流顺序产出 ("run", Run) / ("math", XML node)，递归展开包装元素。"""
    for child in container:
        if child.tag == RUN_TAG:
            yield "run", Run(child, parent)
        elif child.tag in MATH_TAGS:
            yield "math", child
        elif child.tag in FLOW_CONTAINER_TAGS:
            yield from _iter_flow(child, parent)


def _paragraph_chunks(paragraph) -> list[tuple[str, bool, Run | None]]:
    """按文档流顺序切分段落：普通 run 保留上标标记，OMML 公式转为纯文本块（run 为 None）。"""
    chunks: list[tuple[str, bool, Run | None]] = []
    for kind, node in _iter_flow(paragraph._p, paragraph):
        if kind == "run":
            if node.text:
                chunks.append((node.text, bool(node.font.superscript), node))
        else:
            text = "".join(part.text or "" for part in node.iter(MATH_TEXT_TAG))
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
            # 横向合并用同一个 `_tc` 连续出现判定；纵向合并须比较底层 `_tc`：
            # python-docx 每次访问 `row.cells` 都会新建 `_Cell` 包装对象，
            # 用 `cell is previous_row[column]` 恒为 False，纵合并永远识别不出来（内容重复）。
            merged = (previous_tc is not None and cell._tc is previous_tc) or (
                column < len(previous_row) and cell._tc is previous_row[column]._tc
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


# 图片题注搜索窗口：先向下（图题在图片下方，中文期刊惯例，与表题在上方相反），
# 找不到再向上（部分英文期刊与 IEEE 模板把图题放在图上方）。两向都必须匹配题注版式。
_CAPTION_LOOKAHEAD = 3
_CAPTION_LOOKBEHIND = 2


def _image_caption(paragraphs: list[Paragraph], anchor_index: int) -> tuple[str, int | None]:
    """图片题注：先向下找 3 段，再向上找 2 段；两向都要求段落匹配 `CAPTION_PATTERN`。

    只认「以 图N/表N/Fig N/Table N 开头」的段落，因此正文里顺带提到图号的句子
    （「如图3所示，模型表现更好。」）不会被误当成题注。
    本仓库 16 篇样本实测：题注全部位于图片下方且全部识别成功；向上分支属版式稳健性补充，
    不改变既有样本的识别结果。
    """
    by_index = {paragraph.index: paragraph for paragraph in paragraphs}

    def find(start: int, stop: int, step: int) -> tuple[str, int | None]:
        for index in range(start, stop, step):
            paragraph = by_index.get(index)
            if paragraph is not None and CAPTION_PATTERN.match(paragraph.text.strip()):
                return paragraph.text.strip(), paragraph.index
        return "", None

    found = find(anchor_index + 1, anchor_index + _CAPTION_LOOKAHEAD + 1, 1)
    if found[1] is not None:
        return found
    return find(anchor_index - 1, anchor_index - _CAPTION_LOOKBEHIND - 1, -1)


def _nearest_paragraph_index(paragraphs: list[Paragraph], block_index: int) -> int:
    """把「原始块序号」映射到实际存在的段落序号。

    纯图片、以图片嵌入的公式、空段不产出 ``Paragraph``（无文本被跳过），但仍占用块序号。
    若直接用块序号作锚点，前端按 ``paragraph_index`` 定位时会找不到该段落（无法高亮/定位）。
    故锚到最近的前一个正文段；没有前序段时退回第一个正文段（与表格锚到其前一段的口径一致）。
    """
    kept = [paragraph.index for paragraph in paragraphs]
    if not kept:
        return 0
    preceding = [index for index in kept if index <= block_index]
    return max(preceding) if preceding else min(kept)


def _save_images(document, path: Path, pending: list[tuple[str, int]], paragraphs: list[Paragraph]) -> list[ImageRef]:
    """把内嵌图片落盘到会话目录下的 `<docx名>_media/`，并返回带锚点的 ImageRef。

    落盘位置在会话临时目录内，因此 `purge_session_files()` 会随会话一并清除（无需额外删除链）。
    """
    if not pending:
        return []
    media_dir = path.parent / f"{path.stem}_media"
    images: list[ImageRef] = []
    for rel_id, block_index in pending:
        part = document.part.related_parts.get(rel_id)
        blob = getattr(part, "blob", b"") if part is not None else b""
        if not blob:
            continue
        media_type = (getattr(part, "content_type", "") or "").lower()
        filename = f"fig{len(images) + 1}.{CONTENT_TYPE_EXT.get(media_type, 'bin')}"
        media_dir.mkdir(parents=True, exist_ok=True)
        (media_dir / filename).write_bytes(blob)
        # 题注搜索按原始块序号（保持既有口径）；锚点则映射到真实存在的段落序号，
        # 避免落到被跳过的空文本段上导致前端无法定位/高亮。
        caption, caption_index = _image_caption(paragraphs, block_index)
        images.append(
            ImageRef(
                id=new_id("img"),
                index=len(images),
                media_type=media_type,
                byte_size=len(blob),
                filename=f"{media_dir.name}/{filename}",
                caption=caption,
                caption_index=caption_index,
                anchor=Anchor(paragraph_index=_nearest_paragraph_index(paragraphs, block_index)),
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

        body_size = _estimate_body_size(document)

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
                is_heading, level, _reason = _looks_like_heading(text, style, run_objects, body_size)
                if is_heading:
                    heuristic_headings += 1
                    if not style or style == "Normal":
                        style = "HeuristicHeading"
            paragraphs.append(
                Paragraph(index=current, text=text, style=style, is_heading=is_heading, sentences=split_sentences(text))
            )
            if is_heading:
                sections.append(
                    Section(
                        id=new_id("sec"),
                        title=text.strip(),
                        level=level,
                        paragraph_index=current,
                        confidence=1.0 if style_heading else 0.7,
                        # 启发式（非 Word 样式）标题的章节边界不可靠，交由前端提示人工确认
                        needs_review=not style_heading,
                    )
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
            if paragraph.is_heading and _is_reference_heading(paragraph.text):
                ref_start = position
                break
        references: dict[int, ReferenceEntry] = {}
        for paragraph in paragraphs[ref_start + 1:]:
            number = _reference_number(paragraph.text)
            if number is not None:
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
            language=_detect_language("\n".join(paragraph.text for paragraph in paragraphs)),
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
