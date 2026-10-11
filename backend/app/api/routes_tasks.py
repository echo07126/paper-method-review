from fastapi import APIRouter, Request, Response

from app.api.deps import get_store, resolve_session
from app.models.schemas import TaskStatusResponse

router = APIRouter(tags=["tasks"])


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task(task_id: str, request: Request, response: Response) -> dict:
    """轮询任务状态：succeeded 时 result 即旧同步响应体；failed 时 error 带 code/message。"""
    store = get_store()
    session_id = resolve_session(request, response, store)
    return store.authorized_job(session_id, task_id)