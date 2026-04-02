"""B 端渠道绑定管理 API。"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.core.security import get_current_admin
from mao.db.database import get_db
from mao.db.models.channel import MaoChannelAccount, MaoChannelSession
from mao.db.models.user import MaoUser

router = APIRouter(prefix="/admin", tags=["B端-渠道管理"])


class BindChannelAccountRequest(BaseModel):
    user_id: str
    channel_type: str = Field(..., pattern="^(FEISHU|DINGTALK|WECOM|WEB)$")
    external_user_id: str
    external_app_id: str


class BindChannelSessionRequest(BaseModel):
    session_id: str
    channel_type: str = Field(..., pattern="^(FEISHU|DINGTALK|WECOM|WEB)$")
    external_chat_id: str
    external_app_id: str


@router.post("/channel-accounts/bind", status_code=status.HTTP_201_CREATED)
async def bind_channel_account(
    req: BindChannelAccountRequest,
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    existed = await db.execute(
        select(MaoChannelAccount).where(
            MaoChannelAccount.channel_type == req.channel_type,
            MaoChannelAccount.external_user_id == req.external_user_id,
            MaoChannelAccount.external_app_id == req.external_app_id,
        )
    )
    row = existed.scalar_one_or_none()
    if row:
        return {"code": 200, "message": "Success", "data": {"binding_id": row.id}}

    account = MaoChannelAccount(
        user_id=req.user_id,
        channel_type=req.channel_type,
        external_user_id=req.external_user_id,
        external_app_id=req.external_app_id,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return {"code": 200, "message": "绑定成功", "data": {"binding_id": account.id}}


@router.get("/channel-accounts")
async def list_channel_accounts(
    channel_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    query = select(MaoChannelAccount)
    if channel_type:
        query = query.where(MaoChannelAccount.channel_type == channel_type)
    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    items = result.scalars().all()
    return {
        "code": 200,
        "message": "Success",
        "data": {
            "items": [
                {
                    "id": i.id,
                    "user_id": i.user_id,
                    "channel_type": i.channel_type,
                    "external_user_id": i.external_user_id,
                    "external_app_id": i.external_app_id,
                }
                for i in items
            ],
            "page_info": {"total": len(items), "current_page": page, "has_more": len(items) == size},
        },
    }


@router.delete("/channel-accounts/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unbind_channel_account(
    binding_id: int,
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(MaoChannelAccount).where(MaoChannelAccount.id == binding_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="binding not found")
    await db.delete(item)
    await db.commit()


@router.post("/channel-sessions/bind", status_code=status.HTTP_201_CREATED)
async def bind_channel_session(
    req: BindChannelSessionRequest,
    _: MaoUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    existed = await db.execute(
        select(MaoChannelSession).where(
            MaoChannelSession.channel_type == req.channel_type,
            MaoChannelSession.external_chat_id == req.external_chat_id,
            MaoChannelSession.external_app_id == req.external_app_id,
        )
    )
    row = existed.scalar_one_or_none()
    if row:
        return {"code": 200, "message": "Success", "data": {"id": row.id}}

    rel = MaoChannelSession(
        session_id=req.session_id,
        channel_type=req.channel_type,
        external_chat_id=req.external_chat_id,
        external_app_id=req.external_app_id,
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)
    return {"code": 200, "message": "绑定成功", "data": {"id": rel.id}}
