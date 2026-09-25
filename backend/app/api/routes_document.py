from fastapi import APIRouter, Request, Response

from app.api.deps import get_store, resolve_session
from app.models.schemas import DocumentResponse

router = APIRouter(tags=["documents"])


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, request: Request, response: Response) -> dict:
    store = get_store()
    session_id = resolve_session(request, response, store)
    document = store.authorized_document(session_id, document_id)
    return {
        "document_id": document_id,
        "source_name": document.get("source_name"),
        "sections": document.get("sections", []),
        "paragraphs": document.get("paragraphs", []),
        "tables": document.get("tables", []),
        "warnings": document.get("warnings", []),
        "parser": document.get("parser"),
    }
