"""
C 端聊天 API 路由
提供用户会话、消息发送（SSE 流式）、GUI 卡片交互、离线信箱等接口。
"""
import asyncio
import json
import logging
from typing import Any, AsyncGenerator

import ulid
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.core.enums import MessageType, TaskStatus
from mao.core.redis_client import sse_subscribe
from mao.core.security import get_current_user
from mao.db.database import get_db
from mao.db.models.message import MaoMessage
from mao.db.models.session import MaoSession
from mao.db.models.task import MaoTask
from mao.db.models.user import MaoUser
from mao.engine.router import IntentRouter
from mao.engine.task_service import TaskService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["C端-对话"])


# ─────────────────────────────────────────────
# 请求/响应 Schema
# ─────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    title: str | None = Field(None, max_length=100, description="会话标题（可选，默认自动生成）")


class CreateSessionResponse(BaseModel):
    session_id: str
    title: str
    created_at: str


class SessionListItem(BaseModel):
    session_id: str
    title: str
    last_message: str | None
    updated_at: str


class SendMessageRequest(BaseModel):
    session_id: str
    content: str = Field(..., min_length=1, max_length=4000, description="用户消息内容")
    idempotency_key: str | None = Field(None, description="幂等键，防止重复提交")




class ChatCompletionRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=4000)
    target_task_id: str | None = None
    context_mode: str | None = "auto"
    source_channel: str | None = "LUI_WORKSPACE"


class ExecuteActionRequest(BaseModel):
    task_id: str
    action_id: str
    action_type: str = Field(..., description="CONFIRM / CANCEL / SUBMIT_FORM / SELECT_INTENT")
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(None, description="幂等键（可通过 Header 传入）")


class OfflineInboxItem(BaseModel):
    inbox_id: int
    task_id: str | None
    message_type: str
    message_content: str | None
    card_schema: dict[str, Any] | None
    created_at: str


# ─────────────────────────────────────────────
# 接口实现
# ─────────────────────────────────────────────

@router.post("/sessions", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    req: CreateSessionRequest,
    current_user: MaoUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreateSessionResponse:
    """创建新会话。"""
    session_id = f"sess_{ulid.new()}"
    title = req.title or f"新对话 {session_id[-6:]}"
    session = MaoSession(
        session_id=session_id,
        user_id=current_user.user_id,
        title=title,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return CreateSessionResponse(
        session_id=session.session_id,
        title=session.title,
        created_at=session.created_at.isoformat(),
    )


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: MaoUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionListItem]:
    """获取当前用户的会话列表（分页）。"""
    offset = (page - 1) * page_size
    result = await db.execute(
        select(MaoSession)
        .where(MaoSession.user_id == current_user.user_id)
        .order_by(MaoSession.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    sessions = result.scalars().all()
    return [
        SessionListItem(
            session_id=s.session_id,
            title=s.title,
            last_message=s.last_message,
            updated_at=s.updated_at.isoformat(),
        )
        for s in sessions
    ]




async def _dispatch_message(
    session_id: str,
    user_content: str,
    idempotency_key: str | None,
    db: AsyncSession,
) -> dict[str, Any]:
    if idempotency_key:
        existing = await db.execute(select(MaoTask).where(MaoTask.idempotency_key == idempotency_key))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Duplicate request (idempotency key already used)")

    user_msg = MaoMessage(session_id=session_id, role="user", content=user_content, message_type=MessageType.TEXT.value)
    db.add(user_msg)

    intent_router = IntentRouter(db)
    route_result = await intent_router.route(user_content)

    if route_result.route_type == "CLARIFICATION_REQUIRED":
        card_schema = {
            "title": "意图澄清",
            "elements": [{"type": "text", "content": "检测到多个可承接对象，请手动选择。"}],
            "actions": [
                {
                    "action_id": f"clarify:{item.get('type')}:{item.get('id')}",
                    "label": item.get("name", "未命名"),
                    "action_type": "SELECT_INTENT",
                    "payload": item,
                }
                for item in route_result.clarification_candidates
            ],
            "client_side_lock": True,
        }
        db.add(MaoMessage(session_id=session_id, role="assistant", message_type=MessageType.CARD.value, card_schema=card_schema))
        await db.commit()
        return {"task_id": None, "status": "SUSPENDED", "route_type": route_result.route_type, "card_schema": card_schema}

    task_service = TaskService(db)
    task = await task_service.create_task(
        session_id=session_id,
        agent_id=route_result.target_id if route_result.route_type == "AGENT" else None,
        workflow_id=route_result.target_id if route_result.route_type == "WORKFLOW" else None,
        idempotency_key=idempotency_key,
    )
    await db.commit()

    if route_result.route_type != "DIRECT_REPLY":
        asyncio.create_task(task_service.run_task(task=task, user_message=user_content, agent_config={}, skill_registry={}))

    return {"task_id": task.task_id, "status": task.status, "route_type": route_result.route_type, "routed_to": route_result.target_name}


@router.post("/completions")
async def chat_completions(
    req: ChatCompletionRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    current_user: MaoUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(MaoSession).where(MaoSession.session_id == req.session_id, MaoSession.user_id == current_user.user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    data = await _dispatch_message(req.session_id, req.message, idempotency_key, db)
    return {"code": 200, "message": "Success", "data": data}


@router.get("/sessions/{session_id}/stream")
async def stream_chat(
    session_id: str,
    current_user: MaoUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    SSE 流式接口：订阅会话的实时推送事件。
    客户端通过 EventSource 连接此接口，接收 STREAM_CHUNK / CARD / TASK_SUMMARY 等事件。
    """
    # 验证会话归属
    result = await db.execute(
        select(MaoSession).where(
            MaoSession.session_id == session_id,
            MaoSession.user_id == current_user.user_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        # 发送连接确认
        yield f"data: {json.dumps({'event': 'connected', 'session_id': session_id})}\n\n"

        # 订阅 Redis SSE 队列
        async for event in sse_subscribe(session_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            # 任务完成或失败时关闭连接
            if event.get("event") in ("task_summary", "task_failed"):
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    req: SendMessageRequest,
    current_user: MaoUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    发送消息并触发 Agent 推演。
    响应立即返回 task_id，实际执行结果通过 SSE 流式推送。
    """
    return await _dispatch_message(session_id, req.content, req.idempotency_key, db)


@router.post("/action/execute")
async def execute_card_action(
    req: ExecuteActionRequest,
    idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
    current_user: MaoUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    GUI 卡片操作提交接口（双态响应）。
    - 若任务可同步完成：返回 status=SYNC_COMPLETED + result
    - 若任务需要异步处理：返回 status=SUSPENDED
    幂等键必填，防止卡片二次触发（配合 client_side_lock 物理防抖）。
    """
    # 幂等检查：同一 idempotency_key 只处理一次
    from mao.core.redis_client import redis_client
    effective_idem = req.idempotency_key or idempotency_key_header
    if not effective_idem:
        raise HTTPException(status_code=400, detail="Idempotency key required")
    idem_key = f"card_action:{effective_idem}"
    if not await redis_client.set(idem_key, "1", nx=True, ex=300):
        raise HTTPException(status_code=409, detail="Duplicate card action (idempotency key already used)")

    # 查找任务
    result = await db.execute(
        select(MaoTask).where(MaoTask.task_id == req.task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != TaskStatus.SUSPENDED.value:
        raise HTTPException(
            status_code=422,
            detail=f"Task is not in SUSPENDED state (current: {task.status})"
        )

    # 将卡片操作结果写入黑板，恢复任务
    callback_payload = {
        "action_id": req.action_id,
        "action_type": req.action_type,
        "payload": req.payload,
        "operator_user_id": current_user.user_id,
    }

    task_service = TaskService(db)
    await task_service.resume_task(
        task=task,
        callback_payload=callback_payload,
        agent_config={},
        skill_registry={},
    )

    # 双态响应：CANCEL 类操作可同步完成
    if req.action_type == "CANCEL":
        await task_service.kill_task(task, reason=f"User cancelled via card action: {req.action_id}")
        return {"status": "SYNC_COMPLETED", "result": {"message": "操作已取消"}}

    # 其他操作异步处理
    return {"status": "SUSPENDED", "task_id": req.task_id}


@router.get("/managed-tasks")
async def list_managed_tasks(
    current_user: MaoUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    获取当前用户的后台托管任务列表（Cron 盯盘任务等）。
    用于 C 端左侧边栏展示。
    """
    from mao.db.models.cron import MaoCronJob
    result = await db.execute(
        select(MaoCronJob).where(
            MaoCronJob.target_user_id == current_user.user_id,
            MaoCronJob.status == "ACTIVE",
        )
    )
    cron_jobs = result.scalars().all()
    return {
        "items": [
            {
                "job_id": j.job_id,
                "name": j.name,
                "cron_expr": j.cron_expr,
                "last_run_at": j.last_run_at.isoformat() if j.last_run_at else None,
                "status": j.status,
            }
            for j in cron_jobs
        ]
    }


@router.get("/offline-inbox", response_model=list[OfflineInboxItem])
async def get_offline_inbox(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: MaoUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OfflineInboxItem]:
    """
    获取当前用户的离线信箱消息列表。
    用户上线后主动拉取，获取离线期间的任务结果和卡片通知。
    """
    offset = (page - 1) * page_size
    result = await db.execute(
        select(MaoOfflineInbox)
        .where(
            MaoOfflineInbox.user_id == current_user.user_id,
            MaoOfflineInbox.is_read == False,  # noqa: E712
        )
        .order_by(MaoOfflineInbox.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = result.scalars().all()
    return [
        OfflineInboxItem(
            inbox_id=item.id,
            task_id=item.task_id,
            message_type=item.message_type,
            message_content=item.message_content,
            card_schema=item.card_schema,
            created_at=item.created_at.isoformat(),
        )
        for item in items
    ]


# 避免循环导入
from mao.db.models.task import MaoOfflineInbox  # noqa: E402
