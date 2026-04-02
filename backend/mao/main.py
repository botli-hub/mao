"""
MAO 平台 FastAPI 应用入口
注册所有路由、启动后台服务（Archiver、InboxRetrier、CronScheduler）。
"""
import asyncio
import logging

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

app = FastAPI(
    title="MAO 营销多智能体协同编排平台",
    description="Marketing Agent Orchestration Platform - Backend API",
    version="9.6.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
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


@app.on_event("startup")
async def startup() -> None:
    """应用启动时初始化后台服务。"""
    logger.info("MAO Platform starting up...")

    # 启动 Cron 调度器
    await start_scheduler()

    # 启动归档服务（后台任务）
    archiver = get_archiver()
    asyncio.create_task(archiver.start())

    # 启动离线信箱重投服务（后台任务）
    retrier = get_inbox_retrier()
    asyncio.create_task(retrier.start())

    logger.info("MAO Platform started successfully")


@app.on_event("shutdown")
async def shutdown() -> None:
    """应用关闭时清理资源。"""
    logger.info("MAO Platform shutting down...")

    await stop_scheduler()

    archiver = get_archiver()
    await archiver.stop()

    retrier = get_inbox_retrier()
    await retrier.stop()

    logger.info("MAO Platform shutdown complete")


@app.get("/health")
async def health_check() -> dict:
    """健康检查接口。"""
    return {"status": "ok", "version": "9.6.0"}
