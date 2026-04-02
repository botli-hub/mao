"""
审计与监控 API
提供全局 Task 监控、强制熔断、执行链路审计（脑电图）、断点续传重试接口。
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.core.security import get_current_admin
from mao.db.database import get_db
from mao.db.models.task import MaoTask, MaoTaskLog, MaoTaskSnapshotArchive
from mao.db.models.user import MaoUser
from mao.engine.task_service import TaskService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["B端-监控审计"])


class RetryTraceRequest(BaseModel):
    resume_mode: str = Field("RETRY_FAILED_NODE", pattern="^(RETRY_FAILED_NODE|SKIP_NODE)$")
    node_id: str | None = None




@router.get("/tasks/active")
async def list_active_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _ = current_admin
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
    result = await db.execute(select(MaoTask).where(MaoTask.task_id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.status in ("COMPLETED", "CANCELLED"):
        raise HTTPException(status_code=422, detail=f"Task is already in terminal state: {task.status}")

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
    _ = current_admin
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
    _ = current_admin
    result = await db.execute(select(MaoTask).where(MaoTask.task_id == trace_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    logs_result = await db.execute(
        select(MaoTaskLog)
        .where(MaoTaskLog.task_id == trace_id)
        .order_by(MaoTaskLog.step_index)
    )
    logs = logs_result.scalars().all()

    total_tokens = {"prompt": 0, "completion": 0, "total": 0}
    steps = []
    for log in logs:
        digest = log.state_digest or {}
        token_usage = digest.get("token_usage", {})
        total_tokens["prompt"] += token_usage.get("prompt", 0)
        total_tokens["completion"] += token_usage.get("completion", 0)
        total_tokens["total"] += token_usage.get("prompt", 0) + token_usage.get("completion", 0)
        steps.append(
            {
                "step_index": log.step_index,
                "step_type": log.step_type,
                "content": log.content,
                "skill_id": getattr(log, "skill_id", None),
                "token_usage": token_usage,
                "execution_version": digest.get("execution_version"),
                "created_at": log.created_at.isoformat(),
            }
        )

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
    req: RetryTraceRequest,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(MaoTask).where(MaoTask.task_id == trace_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    if task.status != "FAILED":
        raise HTTPException(status_code=422, detail=f"Only FAILED tasks can be retried (current: {task.status})")

    task.status = "PENDING"
    task.error_message = None
    if req.resume_mode == "SKIP_NODE" and req.node_id:
        task.suspend_reason = f"SKIP_NODE:{req.node_id}"
    else:
        task.suspend_reason = "RETRY_FAILED_NODE"
    db.add(task)
    await db.commit()

    logger.info(f"Trace {trace_id} retry triggered by admin {current_admin.user_id}")
    return {
        "trace_id": trace_id,
        "status": "PENDING",
        "message": "Task queued for retry. Execution will resume from the requested resume mode.",
        "resume_mode": req.resume_mode,
        "node_id": req.node_id,
    }


@router.get("/audit/traces/{trace_id}/reconstruct")
async def reconstruct_trace(
    trace_id: str,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """审计视角链路重构：优先 Redis，回退 MySQL。"""
    from mao.core.redis_client import state_get_steps

    _ = current_admin
    result = await db.execute(select(MaoTask).where(MaoTask.task_id == trace_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    redis_steps = await state_get_steps(trace_id)
    if redis_steps:
        return {
            "code": 200,
            "message": "Success",
            "data": {
                "trace_id": trace_id,
                "source": "REDIS",
                "is_complete": True,
                "missing_steps": [],
                "steps": redis_steps,
            },
        }

    logs_result = await db.execute(
        select(MaoTaskLog)
        .where(MaoTaskLog.task_id == trace_id)
        .order_by(MaoTaskLog.step_index)
    )
    logs = logs_result.scalars().all()

    if not logs:
        archive_result = await db.execute(
            select(MaoTaskSnapshotArchive)
            .where(MaoTaskSnapshotArchive.task_id == trace_id)
            .order_by(MaoTaskSnapshotArchive.suspend_seq.desc())
            .limit(1)
        )
        archive = archive_result.scalar_one_or_none()
        if archive:
            return {
                "code": 200,
                "message": "Success",
                "data": {
                    "trace_id": trace_id,
                    "source": "MYSQL_ARCHIVE",
                    "is_complete": False,
                    "missing_steps": ["intermediate_steps_may_be_missing"],
                    "steps": archive.snapshot_data.get("steps", []),
                    "blackboard": archive.blackboard_data,
                },
            }

        return {
            "code": 200,
            "message": "Success",
            "data": {
                "trace_id": trace_id,
                "source": "NONE",
                "is_complete": False,
                "missing_steps": ["all_steps_missing"],
                "steps": [],
            },
        }

    indices = [getattr(log, "step_index", getattr(log, "step_seq", 0)) for log in logs]
    max_idx = max(indices) if indices else -1
    missing_steps = sorted(list(set(range(0, max_idx + 1)) - set(indices))) if max_idx >= 0 else []

    steps = [
        {
            "step_index": getattr(log, "step_index", getattr(log, "step_seq", 0)),
            "step_type": log.step_type,
            "content": log.content,
            "state_digest": log.state_digest,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]

    return {
        "code": 200,
        "message": "Success",
        "data": {
            "trace_id": trace_id,
            "source": "MYSQL_RECONSTRUCT",
            "is_complete": len(missing_steps) == 0,
            "missing_steps": missing_steps,
            "steps": steps,
        },
    }
