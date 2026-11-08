from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.api import account, admin, api_keys, openai, public
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.errors import openai_error


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="NodePass",
        version="0.1.0",
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.environment == "development" else None,
    )

    @app.middleware("http")
    async def web_request_security(request: Request, call_next):
        if (
            request.url.path.startswith("/api/")
            and request.method not in {"GET", "HEAD", "OPTIONS"}
            and request.headers.get("origin") not in settings.web_origins
        ):
            return JSONResponse({"detail": "请求来源不受信任，请从本站页面提交"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith(("/api/", "/v1/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/v1/"):
            return openai_error(422, "Invalid request parameters.", code="invalid_request")
        return JSONResponse(
            {
                "detail": "输入格式不正确，请检查邮箱和字段要求",
                "fields": [
                    {"field": ".".join(map(str, error["loc"][1:])), "type": error["type"]}
                    for error in exc.errors()
                ],
            },
            status_code=422,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        if request.url.path.startswith("/v1/"):
            return openai_error(503, "Service temporarily unavailable.", code="service_unavailable")
        return JSONResponse({"detail": "数据库暂时不可用，请稍后重试"}, status_code=503)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if request.url.path.startswith("/v1/"):
            code = {
                401: "invalid_api_key",
                402: "insufficient_quota",
                404: "not_found",
                405: "method_not_allowed",
            }.get(exc.status_code)
            return openai_error(exc.status_code, str(exc.detail), code=code, headers=exc.headers)
        return JSONResponse(
            {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        if request.url.path.startswith("/v1/"):
            return openai_error(500, "Internal server error.", code="internal_error")
        return JSONResponse({"detail": "服务暂时不可用，请稍后重试"}, status_code=500)

    @app.get("/health/live", include_in_schema=False)
    def live():
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    def ready():
        with get_session_factory()() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}

    app.include_router(public.router)
    app.include_router(account.router)
    app.include_router(admin.router)
    app.include_router(api_keys.router)
    app.include_router(openai.router)
    return app
