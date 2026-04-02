"""
MAO 平台 FastAPI 应用入口
注册所有路由、启动后台服务（Archiver、InboxRetrier、CronScheduler）。
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mao.api.v1 import chat
from mao.api.v1 import callbacks
from mao.api.v1.admin import skills, agents, audit
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
    """包装后台服务，确保异常可观测，避免静默退出。"""
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
    """应用生命周期：使用 TaskGroup 管理后台常驻任务。"""
    logger.info("MAO Platform starting up...")
    await start_scheduler()

    archiver = get_archiver()
    retrier = get_inbox_retrier()
    shutdown_event = asyncio.Event()

    try:
        async with asyncio.TaskGroup() as tg:
            archiver_task = tg.create_task(
                _run_background_service("archiver", archiver.start, shutdown_event)
            )
            retrier_task = tg.create_task(
                _run_background_service("inbox_retrier", retrier.start, shutdown_event)
            )
            logger.info("MAO Platform started successfully")
            yield

            logger.info("MAO Platform shutting down...")
            shutdown_event.set()
            await archiver.stop()
            await retrier.stop()
            archiver_task.cancel()
            retrier_task.cancel()
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

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(chat.router, prefix="/api/v1")
app.include_router(callbacks.router, prefix="/api/v1")
app.include_router(skills.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict:
    """健康检查接口。"""
    return {"status": "ok", "version": "9.6.0"}
