from fastapi import APIRouter, Request, Response

from app.api.deps import SESSION_COOKIE, get_store, resolve_session
from app.core.audit import audit
from app.core.config import get_settings
from app.models.schemas import PurgeResponse
from app.storage.files import purge_session_files

router = APIRouter(tags=["session"])


@router.post("/sessions/purge", response_model=PurgeResponse)
def purge(request: Request, response: Response) -> dict:
    settings = get_settings()
    store = get_store()
    session_id = resolve_session(request, response, store)
    purge_session_files(settings.temp_dir, session_id)
    store.purge_session(session_id)
    response.delete_cookie(SESSION_COOKIE)
    audit("session_purge", session_id=session_id)
    return {"status": "purged"}
