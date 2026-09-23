from fastapi import Request, Response

from app.core.config import Settings, get_settings
from app.storage.repository import Store

SESSION_COOKIE = "pm_session"
COOKIE_SECURE = True


def get_store() -> Store:
    return Store(get_settings().db_path)


def resolve_session(request: Request, response: Response | None = None, store: Store | None = None) -> str:
    settings = get_settings()
    store = store or get_store()
    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        session_id = store.get_session_by_token(token)
        if session_id:
            return session_id
    session_id, new_token = store.create_session(settings.session_ttl_hours)
    if response is not None:
        response.set_cookie(
            SESSION_COOKIE,
            new_token,
            httponly=True,
            secure=settings.app_env != "dev",
            samesite="lax",
            max_age=settings.session_ttl_hours * 3600,
        )
    return session_id


def get_settings_dep() -> Settings:
    return get_settings()
