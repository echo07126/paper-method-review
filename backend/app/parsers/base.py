from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.models.schemas import DocumentIR


class ParseError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ParserCapabilities:
    pages: bool = False
    superscript: bool = False
    bbox: bool = False
    tables: bool = False
    ocr: bool = False


class DocumentParser(Protocol):
    name: str
    version: str
    capabilities: ParserCapabilities

    def supports(self, filename: str, mime: str | None) -> bool: ...

    def parse(self, path: Path) -> DocumentIR: ...
