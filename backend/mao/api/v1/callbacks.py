"""
统一回调网关 API。
"""
import hashlib
import hmac
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.channel.feishu import get_feishu_adapter
from mao.core.config import get_settings
from mao.core.redis_client import redis_client
from mao.db.database import get_db
from mao.db.models.channel import MaoChannelAccount, MaoChannelSession
from mao.db.models.session import MaoSession
from mao.db.models.task import MaoTask
from mao.engine.task_service import TaskService

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/callbacks", tags=["回调网关"])


class UnifiedCallbackRequest(BaseModel):
    source_system: str = Field(..., description="来源系统标识，如 OA / CRM / FEISHU")
    task_id: str = Field(..., description="要唤醒的任务 ID")
    event_type: str = Field(..., description="事件类型，如 APPROVAL_RESULT / FORM_SUBMITTED")
    payload: dict[str, Any] = Field(default_factory=dict, description="回调数据")


@router.post("/webhook/unified", status_code=status.HTTP_200_OK)
async def unified_webhook(
    req: UnifiedCallbackRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
) -> dict[str, Any]:
    try:
        ts = int(x_timestamp)
        if abs(time.time() - ts) > 300:
            raise HTTPException(status_code=401, detail="Timestamp expired (replay attack detected)")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid timestamp")

    nonce_key = f"callback_nonce:{x_nonce}"
    if not await redis_client.set(nonce_key, "1", nx=True, ex=600):
        raise HTTPException(status_code=401, detail="Nonce already used (replay attack detected)")

    body = await request.body()
    expected_sig = hmac.new(
        settings.callback_secret_key.encode(),
        f"{x_timestamp}{x_nonce}{body.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_sig, x_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    result = await db.execute(select(MaoTask).where(MaoTask.task_id == req.task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {req.task_id} not found")

    if task.status != "SUSPENDED":
        return {"received": True, "task_id": req.task_id, "message": f"Task not suspended: {task.status}"}

    task_service = TaskService(db)
    await task_service.resume_task(
        task=task,
        callback_payload={"source_system": req.source_system, "event_type": req.event_type, **req.payload},
        agent_config={},
        skill_registry={},
    )
    return {"received": True, "task_id": req.task_id, "status": "RESUMED"}


@router.post("/channel/feishu", status_code=status.HTTP_200_OK)
async def feishu_event_webhook(
    payload: dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_lark_signature: str | None = Header(None, alias="X-Lark-Signature"),
    x_lark_request_timestamp: str | None = Header(None, alias="X-Lark-Request-Timestamp"),
    x_lark_request_nonce: str | None = Header(None, alias="X-Lark-Request-Nonce"),
) -> dict[str, Any]:
    """飞书消息事件接收入口（3 秒内 ACK）。"""
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    adapter = get_feishu_adapter()
    if x_lark_signature and x_lark_request_timestamp and x_lark_request_nonce:
        body = await request.body()
        if not adapter.verify_webhook_signature(x_lark_request_timestamp, x_lark_request_nonce, body.decode()):
            raise HTTPException(status_code=401, detail="Invalid Feishu signature")

    event = payload.get("event", {})
    sender = event.get("sender", {}).get("sender_id", {})
    message = event.get("message", {})
    open_id = sender.get("open_id")
    chat_id = message.get("chat_id")

    if not open_id or not chat_id:
        return {"code": 0}

    account_result = await db.execute(
        select(MaoChannelAccount).where(
            MaoChannelAccount.channel_type == "FEISHU",
            MaoChannelAccount.external_user_id == open_id,
        )
    )
    account = account_result.scalar_one_or_none()
    if not account:
        logger.warning("No bound channel account for open_id=%s", open_id)
        return {"code": 0}

    sess_result = await db.execute(
        select(MaoChannelSession).where(
            MaoChannelSession.channel_type == "FEISHU",
            MaoChannelSession.external_chat_id == chat_id,
        )
    )
    channel_session = sess_result.scalar_one_or_none()
    if channel_session:
        session_id = channel_session.session_id
    else:
        session = MaoSession(session_id=f"sess_{int(time.time()*1000)}", user_id=account.user_id, title="飞书会话")
        db.add(session)
        channel_session = MaoChannelSession(session_id=session.session_id, channel_type="FEISHU", external_chat_id=chat_id)
        db.add(channel_session)
        await db.commit()
        session_id = session.session_id

    # 仅 ACK，异步处理留给后续事件总线（P1）
    logger.info("Feishu inbound message accepted, session_id=%s", session_id)
    return {"code": 0}


@router.post("/channel/feishu/card-action", status_code=status.HTTP_200_OK)
async def feishu_card_action(
    payload: dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_lark_signature: str | None = Header(None, alias="X-Lark-Signature"),
    x_lark_request_timestamp: str | None = Header(None, alias="X-Lark-Request-Timestamp"),
    x_lark_request_nonce: str | None = Header(None, alias="X-Lark-Request-Nonce"),
) -> dict[str, Any]:
    adapter = get_feishu_adapter()
    if x_lark_signature and x_lark_request_timestamp and x_lark_request_nonce:
        body = await request.body()
        if not adapter.verify_webhook_signature(x_lark_request_timestamp, x_lark_request_nonce, body.decode()):
            raise HTTPException(status_code=401, detail="Invalid Feishu signature")

    callback_data = adapter.parse_card_callback(payload)
    action_id = callback_data.get("action_id")
    if not action_id:
        return {"msg": "no action_id, ignored"}

    parts = action_id.split(":", 1)
    if len(parts) != 2:
        return {"msg": "invalid action_id format"}

    task_id, _ = parts
    result = await db.execute(select(MaoTask).where(MaoTask.task_id == task_id))
    task = result.scalar_one_or_none()
    if not task or task.status != "SUSPENDED":
        return {"msg": "task not found or not suspended"}

    task_service = TaskService(db)
    await task_service.resume_task(
        task=task,
        callback_payload={"source_system": "FEISHU", "event_type": "CARD_ACTION", **callback_data},
        agent_config={},
        skill_registry={},
    )
    return {
        "toast": {"type": "success", "content": "已确认，任务正在执行中..."},
        "card": {"config": {"update_multi": False}},
    }


# backward-compatible alias
@router.post("/feishu/card", status_code=status.HTTP_200_OK)
async def feishu_card_callback_alias(
    payload: dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_lark_signature: str | None = Header(None, alias="X-Lark-Signature"),
    x_lark_request_timestamp: str | None = Header(None, alias="X-Lark-Request-Timestamp"),
    x_lark_request_nonce: str | None = Header(None, alias="X-Lark-Request-Nonce"),
) -> dict[str, Any]:
    return await feishu_card_action(
        payload=payload,
        request=request,
        db=db,
        x_lark_signature=x_lark_signature,
        x_lark_request_timestamp=x_lark_request_timestamp,
        x_lark_request_nonce=x_lark_request_nonce,
    )
