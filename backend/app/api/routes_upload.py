from pathlib import Path

from fastapi import APIRouter, File, Request, Response, UploadFile

from app.api.deps import get_store, resolve_session
from app.core.config import get_settings
from app.core.errors import AppError
from app.parsers.registry import parse_document
from app.models.schemas import UploadResponse
from app.storage.files import save_upload

router = APIRouter(tags=["documents"])


@router.post("/uploads", response_model=UploadResponse)
async def upload_document(request: Request, response: Response, file: UploadFile = File(...)) -> dict:
    settings = get_settings()
    store = get_store()
    session_id = resolve_session(request, response, store)

    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise AppError("file_too_large", f"文件超过 {settings.max_upload_mb}MB 限制。", 413)

    path: Path = save_upload(settings.temp_dir, session_id, file.filename or "upload.docx", content, settings.max_upload_mb)
    document = parse_document(path, file.filename or path.name, file.content_type)
    document_id = store.save_document(session_id, document.source_name, document.model_dump_json())

    return {
        "document_id": document_id,
        "parser": document.parser,
        "sections": [{"title": section.title, "paragraph_index": section.paragraph_index, "needs_review": section.needs_review} for section in document.sections],
        "paragraph_count": len(document.paragraphs),
        "citation_count": len(document.citations),
        "reference_count": len(document.references),
        "warnings": document.warnings,
    }
