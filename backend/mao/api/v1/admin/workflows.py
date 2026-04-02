"""B 端 Workflow 画布 API。"""
from typing import Any

import ulid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.core.security import get_current_admin
from mao.db.database import get_db
from mao.db.models.skill import MaoSkill
from mao.db.models.user import MaoUser
from mao.db.models.workflow import MaoWorkflow, MaoWorkflowSnapshot

router = APIRouter(prefix="/admin/workflows", tags=["B端-Workflow画布"])


class WorkflowCreateRequest(BaseModel):
    name: str = Field(..., max_length=128)
    description: str | None = None


class WorkflowSaveRequest(BaseModel):
    name: str
    description: str | None = None
    blackboard_schema: dict[str, Any] | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowPublishRequest(BaseModel):
    version_desc: str | None = None


@router.get("")
async def list_workflows(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(
        select(MaoWorkflow)
        .order_by(MaoWorkflow.updated_at.desc())
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
                    "workflow_id": w.workflow_id,
                    "name": w.name,
                    "description": w.description,
                    "is_draft": w.is_draft,
                    "published_version": w.published_version,
                    "updated_at": w.updated_at.isoformat(),
                }
                for w in items
            ],
            "page_info": {"total": len(items), "current_page": page, "has_more": len(items) == size},
        },
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workflow(
    req: WorkflowCreateRequest,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    workflow = MaoWorkflow(
        workflow_id=f"wf_{ulid.new()}",
        name=req.name,
        description=req.description,
        dag_definition={"nodes": [], "edges": []},
        is_draft=True,
        created_by=current_admin.user_id,
    )
    db.add(workflow)
    await db.commit()
    return {"code": 200, "message": "Success", "data": {"workflow_id": workflow.workflow_id}}


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    workflow = await _get_workflow_or_404(workflow_id, db)
    return {"code": 200, "message": "Success", "data": _workflow_detail(workflow)}


@router.put("/{workflow_id}")
async def save_workflow(
    workflow_id: str,
    req: WorkflowSaveRequest,
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    workflow = await _get_workflow_or_404(workflow_id, db)
    workflow.name = req.name
    workflow.description = req.description
    workflow.dag_definition = {
        "blackboard_schema": req.blackboard_schema or {},
        "nodes": req.nodes,
        "edges": req.edges,
    }
    workflow.is_draft = True
    db.add(workflow)
    await db.commit()
    return {"code": 200, "message": "Success", "data": {"workflow_id": workflow_id, "saved": True}}


@router.post("/{workflow_id}/publish")
async def publish_workflow(
    workflow_id: str,
    req: WorkflowPublishRequest,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    workflow = await _get_workflow_or_404(workflow_id, db)
    version = f"v{ulid.new()[:8]}"
    snapshot = MaoWorkflowSnapshot(
        workflow_id=workflow.workflow_id,
        version=version,
        snapshot_data={
            "name": workflow.name,
            "description": workflow.description,
            "dag_definition": workflow.dag_definition,
            "version_desc": req.version_desc,
        },
        published_by=current_admin.user_id,
    )
    workflow.is_draft = False
    workflow.published_version = version
    db.add(snapshot)
    db.add(workflow)
    await db.commit()
    return {"code": 200, "message": "Success", "data": {"workflow_id": workflow_id, "version": version}}


@router.get("/{workflow_id}/snapshots")
async def list_workflow_snapshots(
    workflow_id: str,
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(
        select(MaoWorkflowSnapshot)
        .where(MaoWorkflowSnapshot.workflow_id == workflow_id)
        .order_by(MaoWorkflowSnapshot.created_at.desc())
    )
    snaps = result.scalars().all()
    return {
        "code": 200,
        "message": "Success",
        "data": {
            "items": [
                {"version": s.version, "published_at": s.created_at.isoformat(), "published_by": s.published_by}
                for s in snaps
            ]
        },
    }


@router.get("/{workflow_id}/snapshots/{version}")
async def get_workflow_snapshot(
    workflow_id: str,
    version: str,
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(
        select(MaoWorkflowSnapshot).where(
            MaoWorkflowSnapshot.workflow_id == workflow_id,
            MaoWorkflowSnapshot.version == version,
        )
    )
    snap = result.scalar_one_or_none()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"code": 200, "message": "Success", "data": {"version": version, "snapshot_data": snap.snapshot_data}}


@router.post("/{workflow_id}/snapshots/{version}/restore")
async def restore_workflow_snapshot(
    workflow_id: str,
    version: str,
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    workflow = await _get_workflow_or_404(workflow_id, db)
    result = await db.execute(
        select(MaoWorkflowSnapshot).where(
            MaoWorkflowSnapshot.workflow_id == workflow_id,
            MaoWorkflowSnapshot.version == version,
        )
    )
    snap = result.scalar_one_or_none()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    workflow.dag_definition = snap.snapshot_data.get("dag_definition", {})
    workflow.name = snap.snapshot_data.get("name", workflow.name)
    workflow.description = snap.snapshot_data.get("description")
    workflow.published_version = version
    workflow.is_draft = False
    db.add(workflow)
    await db.commit()
    return {"code": 200, "message": "Success", "data": {"workflow_id": workflow_id, "restored_version": version}}


@router.post("/{workflow_id}/publish-as-macro")
async def publish_as_macro(
    workflow_id: str,
    current_admin: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    workflow = await _get_workflow_or_404(workflow_id, db)
    if workflow.is_draft:
        raise HTTPException(status_code=422, detail="Publish workflow before macro registration")

    skill = MaoSkill(
        skill_id=f"skill_{ulid.new()}",
        name=f"RunWorkflow_{workflow.workflow_id}",
        skill_type="MACRO",
        description=f"Macro wrapper for workflow {workflow.workflow_id}",
        endpoint_url=None,
        request_schema={"type": "object", "properties": {}},
        response_schema={"type": "object", "properties": {}},
        mao_control_meta={"workflow_id": workflow.workflow_id},
        is_active=True,
    )
    db.add(skill)
    await db.commit()
    return {
        "code": 200,
        "message": "Success",
        "data": {"workflow_id": workflow_id, "macro_skill_id": skill.skill_id, "created_by": current_admin.user_id},
    }


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: str,
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    workflow = await _get_workflow_or_404(workflow_id, db)
    workflow.is_active = False
    db.add(workflow)
    await db.commit()


async def _get_workflow_or_404(workflow_id: str, db: AsyncSession) -> MaoWorkflow:
    result = await db.execute(select(MaoWorkflow).where(MaoWorkflow.workflow_id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    return workflow


def _workflow_detail(workflow: MaoWorkflow) -> dict[str, Any]:
    dag = workflow.dag_definition or {}
    return {
        "workflow_id": workflow.workflow_id,
        "name": workflow.name,
        "description": workflow.description,
        "blackboard_schema": dag.get("blackboard_schema", {}),
        "nodes": dag.get("nodes", []),
        "edges": dag.get("edges", []),
        "is_draft": workflow.is_draft,
        "published_version": workflow.published_version,
    }
