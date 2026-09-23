from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def error_payload(code: str, message: str, request_id: str) -> dict:
    return {"code": code, "message": message, "request_id": request_id}


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "-")
    return JSONResponse(status_code=exc.status, content=error_payload(exc.code, exc.message, request_id))


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "-")
    return JSONResponse(
        status_code=500,
        content=error_payload("internal_error", "服务内部错误，请携带 request_id 反馈。", request_id),
    )
