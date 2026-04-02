"""B 端 Cron 管理 API。"""
from typing import Any

import ulid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.core.security import get_current_admin
from mao.db.database import get_db
from mao.db.models.cron import MaoCronJob
from mao.db.models.user import MaoUser
from mao.engine.cron_scheduler import pause_cron_job, register_cron_job, resume_cron_job, unregister_cron_job

router = APIRouter(prefix="/admin/cron-jobs", tags=["B端-Cron管理"])


class CronCreateRequest(BaseModel):
    task_intent: str
    cron_expression: str
    timezone: str = "Asia/Shanghai"
    overlap_policy: str = "SKIP"
    target_type: str = Field(..., pattern="^(AGENT|WORKFLOW)$")
    target_ref_id: str
    auth_impersonation: dict[str, Any] | None = None
    retry_policy: dict[str, Any] | None = None
    fallback_action: dict[str, Any] | None = None


class CronUpdateRequest(BaseModel):
    task_intent: str | None = None
    cron_expression: str | None = None
    timezone: str | None = None
    overlap_policy: str | None = None
    auth_impersonation: dict[str, Any] | None = None
    retry_policy: dict[str, Any] | None = None
    fallback_action: dict[str, Any] | None = None


class CronToggleRequest(BaseModel):
    target_status: str = Field(..., pattern="^(PAUSED|ACTIVE)$")


@router.get("")
async def list_cron_jobs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(
        select(MaoCronJob)
        .order_by(MaoCronJob.updated_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    items = result.scalars().all()
    return {
        "code": 200,
        "message": "Success",
        "data": {
            "items": [
                {
                    "job_id": j.job_id,
                    "task_intent": j.trigger_message,
                    "cron_expression": j.cron_expr,
                    "timezone": j.timezone,
                    "status": j.status,
                    "overlap_policy": j.overlap_policy,
                    "target_type": "AGENT" if j.description == "AGENT" else "WORKFLOW",
                    "target_ref_id": j.target_session_id,
                }
                for j in items
            ],
            "page_info": {"total": len(items), "current_page": page, "has_more": len(items) == size},
        },
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_cron_job(
    req: CronCreateRequest,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    job = MaoCronJob(
        job_id=f"cron_{ulid.new()}",
        name=f"Cron_{ulid.new()[:6]}",
        description=req.target_type,
        cron_expr=req.cron_expression,
        timezone=req.timezone,
        trigger_message=req.task_intent,
        target_session_id=req.target_ref_id,
        target_user_id=current_admin.user_id,
        overlap_policy=req.overlap_policy,
        auth_impersonation=req.auth_impersonation,
        retry_policy=req.retry_policy,
        fallback_action=req.fallback_action,
        created_by=current_admin.user_id,
        status="ACTIVE",
    )
    db.add(job)
    await db.commit()
    await register_cron_job(job)
    return {"code": 200, "message": "Success", "data": {"job_id": job.job_id}}


@router.put("/{job_id}")
async def update_cron_job(
    job_id: str,
    req: CronUpdateRequest,
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    job = await _get_job_or_404(job_id, db)
    if req.task_intent is not None:
        job.trigger_message = req.task_intent
    if req.cron_expression is not None:
        job.cron_expr = req.cron_expression
    if req.timezone is not None:
        job.timezone = req.timezone
    if req.overlap_policy is not None:
        job.overlap_policy = req.overlap_policy
    if req.auth_impersonation is not None:
        job.auth_impersonation = req.auth_impersonation
    if req.retry_policy is not None:
        job.retry_policy = req.retry_policy
    if req.fallback_action is not None:
        job.fallback_action = req.fallback_action
    db.add(job)
    await db.commit()
    await register_cron_job(job)
    return {"code": 200, "message": "Success", "data": {"job_id": job_id, "updated": True}}


@router.patch("/{job_id}/toggle")
async def toggle_cron_job(
    job_id: str,
    req: CronToggleRequest,
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    job = await _get_job_or_404(job_id, db)
    job.status = req.target_status
    db.add(job)
    await db.commit()
    if req.target_status == "PAUSED":
        await pause_cron_job(job_id)
    else:
        await resume_cron_job(job_id)
    return {"code": 200, "message": "Success", "data": {"job_id": job_id, "status": req.target_status}}


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cron_job(
    job_id: str,
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    job = await _get_job_or_404(job_id, db)
    job.status = "DISABLED"
    db.add(job)
    await db.commit()
    await unregister_cron_job(job_id)


async def _get_job_or_404(job_id: str, db: AsyncSession) -> MaoCronJob:
    result = await db.execute(select(MaoCronJob).where(MaoCronJob.job_id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Cron job not found")
    return job
