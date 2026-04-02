"""
统一回调网关 API
接收外部系统（OA、CRM、飞书卡片等）的回调事件，唤醒挂起任务。
包含防重放安全验证（X-Timestamp / X-Nonce / X-Signature）。
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


class FeishuCardCallbackRequest(BaseModel):
    """飞书卡片回调事件（由飞书平台发送）。"""
    challenge: str | None = None  # 飞书 URL 验证
    type: str | None = None
    action: dict[str, Any] | None = None
    open_message_id: str | None = None
    open_chat_id: str | None = None
    operator: dict[str, Any] | None = None


@router.post("/webhook/unified", status_code=status.HTTP_200_OK)
async def unified_webhook(
    req: UnifiedCallbackRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
) -> dict[str, Any]:
    """
    统一回调入口。
    安全验证：防重放攻击（时间戳 + Nonce + HMAC-SHA256 签名）。
    """
    # 1. 验证时间戳（允许 5 分钟偏差）
    try:
        ts = int(x_timestamp)
        if abs(time.time() - ts) > 300:
            raise HTTPException(status_code=401, detail="Timestamp expired (replay attack detected)")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid timestamp")

    # 2. 验证 Nonce 唯一性（防重放）
    nonce_key = f"callback_nonce:{x_nonce}"
    if not await redis_client.set(nonce_key, "1", nx=True, ex=600):
        raise HTTPException(status_code=401, detail="Nonce already used (replay attack detected)")

    # 3. 验证 HMAC-SHA256 签名
    body = await request.body()
    expected_sig = hmac.new(
        settings.callback_secret_key.encode(),
        f"{x_timestamp}{x_nonce}{body.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_sig, x_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 4. 查找并唤醒任务
    result = await db.execute(
        select(MaoTask).where(MaoTask.task_id == req.task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {req.task_id} not found")

    if task.status != "SUSPENDED":
        return {
            "received": True,
            "task_id": req.task_id,
            "message": f"Task is not SUSPENDED (current: {task.status}), callback ignored",
        }

    # 5. 恢复任务执行
    task_service = TaskService(db)
    await task_service.resume_task(
        task=task,
        callback_payload={
            "source_system": req.source_system,
            "event_type": req.event_type,
            **req.payload,
        },
        agent_config={},
        skill_registry={},
    )

    logger.info(f"Task {req.task_id} resumed by callback from {req.source_system}")
    return {"received": True, "task_id": req.task_id, "status": "RESUMED"}


@router.post("/feishu/card", status_code=status.HTTP_200_OK)
async def feishu_card_callback(
    payload: dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_lark_signature: str | None = Header(None, alias="X-Lark-Signature"),
    x_lark_request_timestamp: str | None = Header(None, alias="X-Lark-Request-Timestamp"),
    x_lark_request_nonce: str | None = Header(None, alias="X-Lark-Request-Nonce"),
) -> dict[str, Any]:
    """
    飞书卡片回调入口。
    处理用户点击飞书 Interactive Card 按钮的事件。
    """
    # 飞书 URL 验证（首次配置时）
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    # 验证飞书签名
    if x_lark_signature and x_lark_request_timestamp and x_lark_request_nonce:
        body = await request.body()
        adapter = get_feishu_adapter()
        if not adapter.verify_webhook_signature(
            x_lark_request_timestamp,
            x_lark_request_nonce,
            body.decode(),
        ):
            raise HTTPException(status_code=401, detail="Invalid Feishu signature")

    # 解析卡片回调
    adapter = get_feishu_adapter()
    callback_data = adapter.parse_card_callback(payload)

    action_id = callback_data.get("action_id")
    if not action_id:
        return {"msg": "no action_id, ignored"}

    # 从 action_id 中提取 task_id（格式：{task_id}:{action_name}）
    parts = action_id.split(":", 1)
    if len(parts) != 2:
        return {"msg": "invalid action_id format"}

    task_id, action_name = parts

    # 查找并唤醒任务
    result = await db.execute(
        select(MaoTask).where(MaoTask.task_id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task or task.status != "SUSPENDED":
        return {"msg": "task not found or not suspended"}

    task_service = TaskService(db)
    await task_service.resume_task(
        task=task,
        callback_payload={
            "source_system": "FEISHU",
            "event_type": "CARD_ACTION",
            **callback_data,
        },
        agent_config={},
        skill_registry={},
    )

    # 更新飞书卡片状态（将按钮置为已处理）
    if callback_data.get("message_id"):
        try:
            updated_card = {"title": "已处理", "elements": [{"type": "text", "content": "操作已提交，处理中..."}]}
            await adapter.update_card(callback_data["message_id"], updated_card)
        except Exception as e:
            logger.warning(f"Failed to update Feishu card: {e}")

    return {"msg": "success"}
