import asyncio
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_chat,
    routes_compare,
    routes_document,
    routes_health,
    routes_report,
    routes_review,
    routes_session,
    routes_upload,
)
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler, unhandled_error_handler
from app.core.logging import safe_logger, setup_logging
from app.core.ratelimit import enforce as enforce_rate_limit
from app.storage.cleanup_task import CLEANUP_INTERVAL_SECONDS, periodic_cleanup
from app.storage.db import init_db
from app.storage.maintenance import cleanup_expired


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging()
    settings.guard_production()

    env_key = os.environ.get("DEEPSEEK_API_KEY", "")
    effective_key = settings.deepseek_api_key
    if env_key and env_key != effective_key:
        safe_logger().warning(
            "env_key_conflict: 环境变量 Key(尾号 %s) 与 .env(尾号 %s) 不一致，按 .env 生效；"
            "如需彻底消除该环境变量，请在宿主应用/启动脚本层面清理后重启应用。",
            env_key[-6:],
            effective_key[-6:],
        )
    safe_logger().info(
        "llm_key_effective tail=%s model=%s base_url=%s",
        effective_key[-6:],
        settings.deepseek_model,
        settings.deepseek_base_url,
    )

    init_db(settings.db_path)
    os.makedirs(settings.temp_dir, exist_ok=True)
    # 启动时先清一次（覆盖上次进程残留），再交由常驻任务周期性执行
    cleanup_expired(settings.db_path, settings.temp_dir)
    cleanup_task = asyncio.create_task(
        periodic_cleanup(settings.db_path, settings.temp_dir, CLEANUP_INTERVAL_SECONDS)
    )
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="论文方法论审查助手 API",
        version="0.1.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials="*" not in settings.origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex[:12]
        try:
            enforce_rate_limit(request)
        except AppError as exc:
            # 中间件抛出的异常不会进入 AppError 处理器（会被外层 ServerErrorMiddleware 归为 500），
            # 这里就地复用处理器返回一致的 429 响应体。
            return await app_error_handler(request, exc)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    prefix = "/api/v1"
    for router in (
        routes_health.router,
        routes_upload.router,
        routes_document.router,
        routes_review.router,
        routes_report.router,
        routes_chat.router,
        routes_compare.router,
        routes_session.router,
    ):
        app.include_router(router, prefix=prefix)
    return app


app = create_app()
