from pathlib import Path

from app.core.errors import AppError
from app.models.schemas import DocumentIR
from app.parsers.base import ParseError
from app.parsers.docx_parser import DocxParser
from app.parsers.pdf_parser import PdfParser

PARSERS = [DocxParser(), PdfParser()]


def select_parser(filename: str, mime: str | None = None):
    for parser in PARSERS:
        if parser.supports(filename, mime):
            return parser
    raise AppError("unsupported_file_type", "仅支持 DOCX 或 PDF 文件。", 400)


def parse_document(path: Path, filename: str, mime: str | None = None) -> DocumentIR:
    parser = select_parser(filename, mime)
    try:
        return parser.parse(path)
    except ParseError as exc:
        raise AppError(exc.code, exc.message, 422) from exc
