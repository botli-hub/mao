"""
审计与监控 API
提供全局 Task 监控、强制熔断、执行链路审计（脑电图）、断点续传重试接口。
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.core.security import get_current_admin
from mao.db.database import get_db
from mao.db.models.task import MaoTask, MaoTaskLog, MaoTaskSnapshotArchive
from mao.db.models.user import MaoUser
from mao.engine.task_service import TaskService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["B端-监控审计"])


@router.get("/tasks/active")
async def list_active_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """获取全局活跃任务列表（RUNNING + SUSPENDED）。"""
    result = await db.execute(
        select(MaoTask)
        .where(MaoTask.status.in_(["RUNNING", "SUSPENDED"]))
        .order_by(MaoTask.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    tasks = result.scalars().all()
    return {
        "items": [
            {
                "task_id": t.task_id,
                "session_id": t.session_id,
                "agent_id": t.agent_id,
                "status": t.status,
                "suspend_reason": t.suspend_reason,
                "updated_at": t.updated_at.isoformat(),
            }
            for t in tasks
        ]
    }


@router.post("/tasks/{task_id}/kill", status_code=status.HTTP_200_OK)
async def kill_task(
    task_id: str,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    强制熔断任务（管理员操作）。
    释放分布式锁，将任务状态置为 CANCELLED，清理 Redis StateDB。
    """
    result = await db.execute(select(MaoTask).where(MaoTask.task_id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.status in ("COMPLETED", "CANCELLED"):
        raise HTTPException(
            status_code=422,
            detail=f"Task is already in terminal state: {task.status}"
        )

    task_service = TaskService(db)
    await task_service.kill_task(task, reason=f"Force killed by admin {current_admin.user_id}")

    logger.warning(f"Task {task_id} force killed by admin {current_admin.user_id}")
    return {"task_id": task_id, "status": "CANCELLED", "killed_by": current_admin.user_id}


@router.get("/audit/traces")
async def list_traces(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    task_status: str | None = Query(None, alias="status"),
    agent_id: str | None = Query(None),
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """获取全局执行 Trace 列表（支持按状态、Agent 过滤）。"""
    query = select(MaoTask).order_by(MaoTask.created_at.desc())
    if task_status:
        query = query.where(MaoTask.status == task_status)
    if agent_id:
        query = query.where(MaoTask.agent_id == agent_id)
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    tasks = result.scalars().all()
    return {
        "items": [
            {
                "trace_id": t.task_id,
                "session_id": t.session_id,
                "agent_id": t.agent_id,
                "status": t.status,
                "created_at": t.created_at.isoformat(),
                "updated_at": t.updated_at.isoformat(),
            }
            for t in tasks
        ]
    }


@router.get("/audit/traces/{trace_id}")
async def get_trace_detail(
    trace_id: str,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    获取单次执行的脑电图详情。
    包含：任务元数据、完整执行步骤链路、Token 消耗统计。
    """
    result = await db.execute(select(MaoTask).where(MaoTask.task_id == trace_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    # 获取执行日志（Task Scratchpad）
    logs_result = await db.execute(
        select(MaoTaskLog)
        .where(MaoTaskLog.task_id == trace_id)
        .order_by(MaoTaskLog.step_index)
    )
    logs = logs_result.scalars().all()

    # 汇总 Token 消耗
    total_tokens = {"prompt": 0, "completion": 0, "total": 0}
    steps = []
    for log in logs:
        digest = log.state_digest or {}
        token_usage = digest.get("token_usage", {})
        total_tokens["prompt"] += token_usage.get("prompt", 0)
        total_tokens["completion"] += token_usage.get("completion", 0)
        total_tokens["total"] += token_usage.get("prompt", 0) + token_usage.get("completion", 0)
        steps.append({
            "step_index": log.step_index,
            "step_type": log.step_type,
            "content": log.content,
            "skill_id": log.skill_id,
            "token_usage": token_usage,
            "execution_version": digest.get("execution_version"),
            "created_at": log.created_at.isoformat(),
        })

    return {
        "trace_id": trace_id,
        "session_id": task.session_id,
        "agent_id": task.agent_id,
        "workflow_id": task.workflow_id,
        "status": task.status,
        "total_tokens": total_tokens,
        "step_count": len(steps),
        "steps": steps,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


@router.post("/audit/traces/{trace_id}/retry")
async def retry_trace(
    trace_id: str,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    断点续传重试（从失败节点恢复执行）。
    仅允许对 FAILED 状态的任务执行此操作。
    """
    result = await db.execute(select(MaoTask).where(MaoTask.task_id == trace_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    if task.status != "FAILED":
        raise HTTPException(
            status_code=422,
            detail=f"Only FAILED tasks can be retried (current: {task.status})"
        )

    # 重置任务状态为 PENDING，触发重新执行
    task.status = "PENDING"
    task.error_message = None
    db.add(task)
    await db.commit()

    logger.info(f"Trace {trace_id} retry triggered by admin {current_admin.user_id}")
    return {
        "trace_id": trace_id,
        "status": "PENDING",
        "message": "Task queued for retry. Execution will resume from the last successful step.",
    }


@router.get("/audit/traces/{trace_id}/reconstruct")
async def reconstruct_trace(
    trace_id: str,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    执行链路断点还原接口。
    优先从 Redis StateDB 读取完整快照；
    若 Redis 缺失，则通过 MySQL mao_task_log 序列按时间戳重组执行链路。
    """
    from mao.core.redis_client import state_get_steps

    result = await db.execute(select(MaoTask).where(MaoTask.task_id == trace_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    # 优先从 Redis 读取
    redis_steps = await state_get_steps(trace_id)
    if redis_steps:
        return {
            "trace_id": trace_id,
            "source": "redis",
            "is_complete": True,
            "missing_steps": [],
            "steps": redis_steps,
        }

    # Redis 缺失，从 MySQL 重组
    logs_result = await db.execute(
        select(MaoTaskLog)
        .where(MaoTaskLog.task_id == trace_id)
        .order_by(MaoTaskLog.step_index)
    )
    logs = logs_result.scalars().all()

    if not logs:
        # 尝试从快照归档恢复
        archive_result = await db.execute(
            select(MaoTaskSnapshotArchive)
            .where(MaoTaskSnapshotArchive.task_id == trace_id)
            .order_by(MaoTaskSnapshotArchive.suspend_seq.desc())
            .limit(1)
        )
        archive = archive_result.scalar_one_or_none()
        if archive:
            return {
                "trace_id": trace_id,
                "source": "mysql_archive",
                "is_complete": False,
                "missing_steps": ["intermediate_steps_may_be_missing"],
                "steps": archive.snapshot_data.get("steps", []),
                "blackboard": archive.blackboard_data,
            }

        return {
            "trace_id": trace_id,
            "source": "none",
            "is_complete": False,
            "missing_steps": ["all_steps_missing"],
            "steps": [],
        }

    steps = [
        {
            "step_index": log.step_index,
            "step_type": log.step_type,
            "content": log.content,
            "state_digest": log.state_digest,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]

    return {
        "trace_id": trace_id,
        "source": "mysql_task_log",
        "is_complete": True,
        "missing_steps": [],
        "steps": steps,
    }
