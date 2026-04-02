"""
B 端技能管理 API
提供技能的 CRUD、版本管理接口。
"""
import logging

import ulid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from mao.core.security import get_current_admin
from mao.db.database import get_db
from mao.db.models.skill import MaoSkill
from mao.db.models.user import MaoUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/skills", tags=["B端-技能管理"])


class SkillCreateRequest(BaseModel):
    name: str = Field(..., max_length=64)
    skill_type: str = Field(..., description="API / VIEW / ASYNC / MACRO")
    description: str | None = None
    endpoint_url: str | None = None
    http_method: str = "POST"
    request_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    mao_control_meta: dict[str, Any] | None = Field(
        None,
        description="MAO 控制元数据：x_mao_suspend / ttl_seconds / callback_expect"
    )
    timeout_seconds: int = 30
    is_active: bool = True


class SkillUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    endpoint_url: str | None = None
    request_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    mao_control_meta: dict[str, Any] | None = None
    timeout_seconds: int | None = None
    is_active: bool | None = None


class SkillResponse(BaseModel):
    skill_id: str
    name: str
    skill_type: str
    description: str | None
    endpoint_url: str | None
    is_active: bool
    created_at: str
    updated_at: str


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(
    req: SkillCreateRequest,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SkillResponse:
    """注册新技能。"""
    skill_id = f"skill_{ulid.new()}"
    skill = MaoSkill(
        skill_id=skill_id,
        name=req.name,
        skill_type=req.skill_type,
        description=req.description,
        endpoint_url=req.endpoint_url,
        http_method=req.http_method,
        request_schema=req.request_schema,
        response_schema=req.response_schema,
        mao_control_meta=req.mao_control_meta,
        timeout_seconds=req.timeout_seconds,
        is_active=req.is_active,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return _to_skill_response(skill)


@router.get("", response_model=list[SkillResponse])
async def list_skills(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    skill_type: str | None = Query(None),
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> list[SkillResponse]:
    """获取技能列表（分页）。"""
    query = select(MaoSkill)
    if skill_type:
        query = query.where(MaoSkill.skill_type == skill_type)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    skills = result.scalars().all()
    return [_to_skill_response(s) for s in skills]


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: str,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SkillResponse:
    """获取技能详情。"""
    skill = await _get_skill_or_404(skill_id, db)
    return _to_skill_response(skill)


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str,
    req: SkillUpdateRequest,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SkillResponse:
    """更新技能配置。"""
    skill = await _get_skill_or_404(skill_id, db)
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(skill, field, value)
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return _to_skill_response(skill)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: str,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    删除技能（软删除：将 is_active 置为 False）。
    注意：已被 Agent 引用的技能不允许直接删除。
    """
    skill = await _get_skill_or_404(skill_id, db)
    # 检查是否被 Agent 引用
    from mao.db.models.agent import MaoAgentSkillRel
    ref_result = await db.execute(
        select(MaoAgentSkillRel).where(MaoAgentSkillRel.skill_id == skill_id)
    )
    if ref_result.scalar_one_or_none():
        raise HTTPException(
            status_code=422,
            detail="Cannot delete skill that is referenced by an agent. Remove the skill from all agents first."
        )
    skill.is_active = False
    db.add(skill)
    await db.commit()


# ─── 辅助函数 ───────────────────────────────

async def _get_skill_or_404(skill_id: str, db: AsyncSession) -> MaoSkill:
    result = await db.execute(select(MaoSkill).where(MaoSkill.skill_id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return skill


def _to_skill_response(skill: MaoSkill) -> SkillResponse:
    return SkillResponse(
        skill_id=skill.skill_id,
        name=skill.name,
        skill_type=skill.skill_type,
        description=skill.description,
        endpoint_url=skill.endpoint_url,
        is_active=skill.is_active,
        created_at=skill.created_at.isoformat(),
        updated_at=skill.updated_at.isoformat(),
    )
