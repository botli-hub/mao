"""
B 端 Agent 工厂 API
提供 Agent 的 CRUD、草稿/发布两态管理、快照溯源与回滚接口。
"""
import json
import logging
from typing import Any

import ulid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.core.security import get_current_admin
from mao.db.database import get_db
from mao.db.models.agent import MaoAgent, MaoAgentSnapshot, MaoAgentSkillRel
from mao.db.models.skill import MaoSkill
from mao.db.models.user import MaoUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/agents", tags=["B端-Agent工厂"])


class AgentCreateRequest(BaseModel):
    name: str = Field(..., max_length=64)
    description: str | None = None
    system_prompt: str | None = None
    model_config: dict[str, Any] = Field(
        default_factory=lambda: {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.7,
            "max_steps": 10,
        }
    )
    rag_retrieval_config: dict[str, Any] | None = None
    skill_ids: list[str] = Field(default_factory=list)


class AgentUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    model_config: dict[str, Any] | None = None
    rag_retrieval_config: dict[str, Any] | None = None
    skill_ids: list[str] | None = None


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    description: str | None
    is_draft: bool
    current_version: str | None
    skill_count: int
    created_at: str
    updated_at: str


class AgentSnapshotResponse(BaseModel):
    snapshot_id: str
    version: str
    published_at: str
    published_by: str


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    req: AgentCreateRequest,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    """创建 Agent（草稿态）。"""
    agent_id = f"agent_{ulid.new()}"
    agent = MaoAgent(
        agent_id=agent_id,
        name=req.name,
        description=req.description,
        system_prompt=req.system_prompt,
        model_config=req.model_config,
        rag_retrieval_config=req.rag_retrieval_config,
        is_draft=True,
        is_active=True,
    )
    db.add(agent)
    await db.flush()

    # 绑定技能
    await _bind_skills(agent_id, req.skill_ids, db)
    await db.commit()
    return await _to_agent_response(agent, db)


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AgentResponse]:
    """获取 Agent 列表（分页）。"""
    result = await db.execute(
        select(MaoAgent)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    agents = result.scalars().all()
    return [await _to_agent_response(a, db) for a in agents]


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    req: AgentUpdateRequest,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    """更新 Agent 配置（只能更新草稿态）。"""
    agent = await _get_agent_or_404(agent_id, db)
    if not agent.is_draft:
        raise HTTPException(
            status_code=422,
            detail="Cannot update a published agent. Create a new draft version first."
        )
    for field, value in req.model_dump(exclude_none=True).items():
        if field != "skill_ids":
            setattr(agent, field, value)
    if req.skill_ids is not None:
        # 重新绑定技能
        await db.execute(
            MaoAgentSkillRel.__table__.delete().where(
                MaoAgentSkillRel.agent_id == agent_id
            )
        )
        await _bind_skills(agent_id, req.skill_ids, db)
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return await _to_agent_response(agent, db)


@router.post("/{agent_id}/publish")
async def publish_agent(
    agent_id: str,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    发布 Agent（草稿 → 正式版）。
    1. 校验宏工具环路（防双引擎死循环）
    2. 生成不可变快照
    3. 将 is_draft 置为 False
    """
    agent = await _get_agent_or_404(agent_id, db)

    # 获取绑定的技能列表
    skill_rels = await db.execute(
        select(MaoAgentSkillRel).where(MaoAgentSkillRel.agent_id == agent_id)
    )
    skill_ids = [r.skill_id for r in skill_rels.scalars().all()]

    # 校验宏工具环路（DFS 检测）
    cycle_path = await _detect_macro_cycle(agent_id, skill_ids, db)
    if cycle_path:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "MACRO_CYCLE_DETECTED",
                "message": "宏工具引用形成环路，可能导致双引擎无限嵌套",
                "cycle_path": cycle_path,
            }
        )

    # 生成快照
    version = f"v{ulid.new()[:8]}"
    snapshot_data = {
        "agent_id": agent_id,
        "name": agent.name,
        "system_prompt": agent.system_prompt,
        "model_config": agent.model_config,
        "rag_retrieval_config": agent.rag_retrieval_config,
        "skill_ids": skill_ids,
    }
    snapshot = MaoAgentSnapshot(
        snapshot_id=f"snap_{ulid.new()}",
        agent_id=agent_id,
        version=version,
        snapshot_data=snapshot_data,
        published_by=current_admin.user_id,
    )
    db.add(snapshot)

    # 更新 Agent 状态
    agent.is_draft = False
    agent.current_version = version
    db.add(agent)
    await db.commit()

    return {
        "agent_id": agent_id,
        "version": version,
        "status": "PUBLISHED",
        "validation": {"macro_cycle": "PASS", "skill_count": len(skill_ids)},
    }


@router.get("/{agent_id}/snapshots", response_model=list[AgentSnapshotResponse])
async def list_snapshots(
    agent_id: str,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AgentSnapshotResponse]:
    """获取 Agent 历史快照列表。"""
    result = await db.execute(
        select(MaoAgentSnapshot)
        .where(MaoAgentSnapshot.agent_id == agent_id)
        .order_by(MaoAgentSnapshot.created_at.desc())
    )
    snapshots = result.scalars().all()
    return [
        AgentSnapshotResponse(
            snapshot_id=s.snapshot_id,
            version=s.version,
            published_at=s.created_at.isoformat(),
            published_by=s.published_by,
        )
        for s in snapshots
    ]


@router.post("/{agent_id}/snapshots/{version}/restore")
async def restore_snapshot(
    agent_id: str,
    version: str,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """一键回滚到指定快照版本。"""
    result = await db.execute(
        select(MaoAgentSnapshot).where(
            MaoAgentSnapshot.agent_id == agent_id,
            MaoAgentSnapshot.version == version,
        )
    )
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Snapshot {version} not found")

    agent = await _get_agent_or_404(agent_id, db)
    snap_data = snapshot.snapshot_data or {}

    # 恢复 Agent 配置
    agent.system_prompt = snap_data.get("system_prompt")
    agent.model_config = snap_data.get("model_config")
    agent.rag_retrieval_config = snap_data.get("rag_retrieval_config")
    agent.current_version = version
    agent.is_draft = False
    db.add(agent)

    # 恢复技能绑定
    await db.execute(
        MaoAgentSkillRel.__table__.delete().where(
            MaoAgentSkillRel.agent_id == agent_id
        )
    )
    await _bind_skills(agent_id, snap_data.get("skill_ids", []), db)
    await db.commit()

    return {"agent_id": agent_id, "restored_version": version, "status": "RESTORED"}


# ─── 辅助函数 ───────────────────────────────

async def _get_agent_or_404(agent_id: str, db: AsyncSession) -> MaoAgent:
    result = await db.execute(select(MaoAgent).where(MaoAgent.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return agent


async def _bind_skills(agent_id: str, skill_ids: list[str], db: AsyncSession) -> None:
    """绑定技能到 Agent，并验证技能存在性。"""
    for order, skill_id in enumerate(skill_ids):
        skill_result = await db.execute(
            select(MaoSkill).where(MaoSkill.skill_id == skill_id, MaoSkill.is_active == True)  # noqa: E712
        )
        if not skill_result.scalar_one_or_none():
            raise HTTPException(status_code=422, detail=f"Skill {skill_id} not found or inactive")
        rel = MaoAgentSkillRel(
            agent_id=agent_id,
            skill_id=skill_id,
            sort_order=order,
        )
        db.add(rel)


async def _detect_macro_cycle(
    agent_id: str,
    skill_ids: list[str],
    db: AsyncSession,
    visited: set[str] | None = None,
    path: list[str] | None = None,
) -> list[str] | None:
    """
    DFS 检测宏工具环路。
    防止 Agent A 挂载的 MACRO 技能内部调用 Agent A 本身，导致双引擎死循环。
    :returns: 环路路径（如 ["agent_A", "macro_skill_X", "agent_A"]），无环路返回 None
    """
    if visited is None:
        visited = set()
    if path is None:
        path = [agent_id]

    if agent_id in visited:
        return path  # 发现环路

    visited.add(agent_id)

    for skill_id in skill_ids:
        skill_result = await db.execute(
            select(MaoSkill).where(MaoSkill.skill_id == skill_id)
        )
        skill = skill_result.scalar_one_or_none()
        if not skill or skill.skill_type != "MACRO":
            continue

        # MACRO 技能内部引用的 Agent ID
        macro_meta = skill.mao_control_meta or {}
        target_agent_id = macro_meta.get("target_agent_id")
        if not target_agent_id:
            continue

        # 递归检测
        sub_rels = await db.execute(
            select(MaoAgentSkillRel).where(MaoAgentSkillRel.agent_id == target_agent_id)
        )
        sub_skill_ids = [r.skill_id for r in sub_rels.scalars().all()]

        cycle = await _detect_macro_cycle(
            target_agent_id,
            sub_skill_ids,
            db,
            visited.copy(),
            path + [skill_id, target_agent_id],
        )
        if cycle:
            return cycle

    return None


async def _to_agent_response(agent: MaoAgent, db: AsyncSession) -> AgentResponse:
    skill_count_result = await db.execute(
        select(MaoAgentSkillRel).where(MaoAgentSkillRel.agent_id == agent.agent_id)
    )
    skill_count = len(skill_count_result.scalars().all())
    return AgentResponse(
        agent_id=agent.agent_id,
        name=agent.name,
        description=agent.description,
        is_draft=agent.is_draft,
        current_version=agent.current_version,
        skill_count=skill_count,
        created_at=agent.created_at.isoformat(),
        updated_at=agent.updated_at.isoformat(),
    )
