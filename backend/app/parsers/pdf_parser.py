from pathlib import Path

from app.models.schemas import DocumentIR
from app.parsers.base import ParseError, ParserCapabilities


class PdfParser:
    """二期实现占位：仅声明接口与能力位，一期调用即返回明确提示。

    这样 PDF 支持只需在二期替换 parse() 实现，无需改动注册表、API 与前端。
    """

    name = "pdf"
    version = "0.0-stub"
    capabilities = ParserCapabilities(pages=False, superscript=False, bbox=False, tables=False, ocr=False)

    def supports(self, filename: str, mime: str | None) -> bool:
        return filename.lower().endswith(".pdf")

    def parse(self, path: Path) -> DocumentIR:
        raise ParseError("pdf_not_implemented", "一期仅支持 DOCX；PDF 解析将在后续版本提供。")
