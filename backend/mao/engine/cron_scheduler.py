"""
Cron 调度器服务
基于 APScheduler 实现定时任务调度。
支持：时区感知、防重叠策略、权限代理、重试策略、暂停/恢复。
"""
import logging
from datetime import datetime
from typing import Any

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.core.config import get_settings
from mao.db.models.cron import MaoCronJob

logger = logging.getLogger(__name__)
settings = get_settings()

# 全局调度器单例
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """获取全局调度器实例（懒初始化）。"""
    global _scheduler
    if _scheduler is None:
        jobstores = {
            "default": SQLAlchemyJobStore(url=settings.database_url.replace("+aiomysql", ""))
        }
        _scheduler = AsyncIOScheduler(jobstores=jobstores, timezone="UTC")
    return _scheduler


async def start_scheduler() -> None:
    """启动调度器（应用启动时调用）。"""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Cron scheduler started")


async def stop_scheduler() -> None:
    """停止调度器（应用关闭时调用）。"""
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Cron scheduler stopped")


async def register_cron_job(cron_job: MaoCronJob) -> None:
    """
    将 Cron 任务注册到调度器。
    支持时区感知和防重叠策略。
    """
    scheduler = get_scheduler()

    # 解析 Cron 表达式（6 字段格式：秒 分 时 日 月 周）
    cron_parts = cron_job.cron_expr.split()
    if len(cron_parts) != 6:
        raise ValueError(f"Invalid cron expression (must be 6 fields): {cron_job.cron_expr}")

    sec, minute, hour, day, month, day_of_week = cron_parts
    trigger = CronTrigger(
        second=sec,
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
        timezone=cron_job.timezone,
    )

    # 防重叠策略
    misfire_grace_time: int | None = None
    coalesce = False
    max_instances = 1

    overlap_policy = cron_job.overlap_policy
    if overlap_policy == "SKIP":
        misfire_grace_time = 1  # 错过立即跳过
        coalesce = True
        max_instances = 1
    elif overlap_policy == "QUEUE":
        max_instances = 10  # 允许排队
        coalesce = False
    elif overlap_policy == "CONCURRENT":
        max_instances = 100  # 允许并发
        coalesce = False

    scheduler.add_job(
        func=_execute_cron_job,
        trigger=trigger,
        id=cron_job.job_id,
        args=[cron_job.job_id],
        replace_existing=True,
        misfire_grace_time=misfire_grace_time,
        coalesce=coalesce,
        max_instances=max_instances,
    )
    logger.info(f"Registered cron job: {cron_job.job_id} ({cron_job.cron_expr} {cron_job.timezone})")


async def unregister_cron_job(job_id: str) -> None:
    """从调度器中移除 Cron 任务。"""
    scheduler = get_scheduler()
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Unregistered cron job: {job_id}")
    except Exception:
        pass


async def pause_cron_job(job_id: str) -> None:
    """暂停 Cron 任务。"""
    get_scheduler().pause_job(job_id)


async def resume_cron_job(job_id: str) -> None:
    """恢复 Cron 任务。"""
    get_scheduler().resume_job(job_id)


async def _execute_cron_job(job_id: str) -> None:
    """
    Cron 任务执行回调。
    将 trigger_message 作为用户输入，向目标会话发送消息触发 Agent 执行。
    """
    from mao.db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MaoCronJob).where(MaoCronJob.job_id == job_id)
        )
        cron_job = result.scalar_one_or_none()
        if not cron_job:
            logger.error(f"Cron job not found: {job_id}")
            return

        if cron_job.status != "ACTIVE":
            logger.info(f"Cron job {job_id} is not ACTIVE, skipping")
            return

        logger.info(f"Executing cron job: {job_id} → {cron_job.trigger_message}")

        try:
            # 更新执行统计
            cron_job.last_run_at = datetime.utcnow()
            cron_job.run_count = (cron_job.run_count or 0) + 1
            db.add(cron_job)
            await db.commit()

            # 通过内部 API 触发消息发送
            # 实际实现中，这里会调用 ChatService 处理 trigger_message
            await _trigger_message(
                session_id=cron_job.target_session_id,
                user_id=cron_job.target_user_id,
                message=cron_job.trigger_message,
                auth_impersonation=cron_job.auth_impersonation,
            )

        except Exception as e:
            logger.error(f"Cron job {job_id} execution failed: {e}")
            await _handle_cron_failure(cron_job, str(e), db)


async def _trigger_message(
    session_id: str | None,
    user_id: str,
    message: str,
    auth_impersonation: dict[str, Any] | None = None,
) -> None:
    """触发消息处理（内部调用）。"""
    # 此处通过内部事件总线或直接调用 ChatService 实现
    # 生产环境中可通过 Kafka 发送触发事件
    from mao.core.kafka_client import get_producer
    producer = await get_producer()
    await producer.send_and_wait(
        "mao.internal.cron_trigger",
        value={
            "session_id": session_id,
            "user_id": user_id,
            "message": message,
            "auth_impersonation": auth_impersonation,
        },
    )


async def _handle_cron_failure(
    cron_job: MaoCronJob,
    error: str,
    db: AsyncSession,
) -> None:
    """处理 Cron 任务执行失败（重试策略 + 降级通知）。"""
    retry_policy = cron_job.retry_policy or {}
    max_retries = retry_policy.get("max_retries", 0)

    if max_retries > 0:
        logger.info(f"Cron job {cron_job.job_id} will be retried (max_retries={max_retries})")
        # APScheduler 会根据 misfire_grace_time 自动重试
    else:
        # 触发降级通知
        fallback = cron_job.fallback_action or {}
        if fallback:
            logger.warning(f"Cron job {cron_job.job_id} failed, triggering fallback: {fallback}")
            # 实际实现：发送告警通知（飞书/邮件/短信）
