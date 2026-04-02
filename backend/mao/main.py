"""
MAO 平台 FastAPI 应用入口
注册所有路由、启动后台服务（Archiver、InboxRetrier、CronScheduler）。
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mao.api.v1 import callbacks, chat
from mao.api.v1.admin import agents, audit, channel_accounts, cron_jobs, skills, workflows
from mao.core.config import get_settings
from mao.engine.cron_scheduler import start_scheduler, stop_scheduler
from mao.services.archiver import get_archiver
from mao.services.inbox_retrier import get_inbox_retrier

logger = logging.getLogger(__name__)
settings = get_settings()


async def _run_background_service(
    name: str,
    runner: Callable[[], Awaitable[None]],
    shutdown_event: asyncio.Event,
) -> None:
    try:
        await runner()
        if not shutdown_event.is_set():
            raise RuntimeError(f"{name} service exited unexpectedly")
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("%s service crashed", name)
        raise


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("MAO Platform starting up...")
    await start_scheduler()

    archiver = get_archiver()
    retrier = get_inbox_retrier()
    shutdown_event = asyncio.Event()

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_run_background_service("archiver", archiver.start, shutdown_event))
            tg.create_task(_run_background_service("inbox_retrier", retrier.start, shutdown_event))
            logger.info("MAO Platform started successfully")
            yield

            logger.info("MAO Platform shutting down...")
            shutdown_event.set()
            await archiver.stop()
            await retrier.stop()
            await stop_scheduler()
            logger.info("MAO Platform shutdown complete")
    finally:
        if not shutdown_event.is_set():
            shutdown_event.set()


app = FastAPI(
    title="MAO 营销多智能体协同编排平台",
    description="Marketing Agent Orchestration Platform - Backend API",
    version="9.6.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)


@app.middleware("http")
async def response_envelope_middleware(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/api/v1"):
        return response
    if response.media_type == "text/event-stream":
        return response

    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return response

    try:
        body = b""
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            body += chunk
        payload = json.loads(body.decode() or "{}")
    except Exception:
        return response

    if isinstance(payload, dict) and {"code", "message", "data"}.issubset(payload.keys()):
        return JSONResponse(status_code=response.status_code, content=payload, headers=dict(response.headers))

    wrapped = {
        "code": response.status_code,
        "message": "Success" if response.status_code < 400 else "Error",
        "data": payload,
    }
    return JSONResponse(status_code=response.status_code, content=wrapped, headers=dict(response.headers))


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "message": exc.detail if isinstance(exc.detail, str) else "Error",
            "data": None,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"code": 500, "message": "Internal Server Error", "data": None})


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api/v1")
app.include_router(callbacks.router, prefix="/api/v1")
app.include_router(skills.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(workflows.router, prefix="/api/v1")
app.include_router(cron_jobs.router, prefix="/api/v1")
app.include_router(channel_accounts.router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "version": "9.6.0"}
