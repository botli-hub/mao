"""
渠道消息分发器（Channel Dispatcher）
根据 channel_type 将 OmniMessage 路由到对应的渠道适配器。
"""
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.channel.base import BaseChannelAdapter, OmniMessage
from mao.channel.feishu import get_feishu_adapter
from mao.channel.dingtalk import get_dingtalk_adapter
from mao.channel.wecom import get_wecom_adapter
from mao.core.enums import ChannelType
from mao.core.redis_client import sse_push
from mao.db.models.channel import MaoChannelSession, MaoOfflineInbox

logger = logging.getLogger(__name__)


class ChannelDispatcher:
    """
    渠道消息分发器。
    负责：
    1. 根据 session_id 查找渠道类型和外部会话 ID
    2. 路由到对应的渠道适配器
    3. 用户离线时写入离线信箱
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._adapters: dict[str, BaseChannelAdapter] = {
            ChannelType.FEISHU.value: get_feishu_adapter(),
            ChannelType.DINGTALK.value: get_dingtalk_adapter(),
            ChannelType.WECOM.value: get_wecom_adapter(),
        }

    async def dispatch(self, session_id: str, omni_message: OmniMessage) -> None:
        """
        分发消息到对应渠道。
        :param session_id: MAO 会话 ID
        :param omni_message: 统一消息对象
        """
        # 查找渠道会话映射
        result = await self.db.execute(
            select(MaoChannelSession).where(
                MaoChannelSession.session_id == session_id
            )
        )
        channel_session = result.scalar_one_or_none()

        if not channel_session:
            # 无渠道映射，默认走 Web SSE 推送
            await self._dispatch_web(session_id, omni_message)
            return

        channel_type = channel_session.channel_type
        external_chat_id = channel_session.external_chat_id

        if channel_type == ChannelType.WEB.value:
            await self._dispatch_web(session_id, omni_message)
        elif channel_type in self._adapters:
            adapter = self._adapters[channel_type]
            try:
                await adapter.send_message(external_chat_id, omni_message)
            except Exception as e:
                logger.warning(f"Channel dispatch failed ({channel_type}): {e}")
                # 写入离线信箱
                await self._write_offline_inbox(
                    session_id=session_id,
                    omni_message=omni_message,
                    channel_type=channel_type,
                )
        else:
            logger.warning(f"No adapter for channel type: {channel_type}")
            await self._dispatch_web(session_id, omni_message)

    async def _dispatch_web(self, session_id: str, omni_message: OmniMessage) -> None:
        """通过 Redis SSE 队列推送 Web 消息。"""
        event: dict[str, Any] = {
            "event": omni_message.message_type.lower(),
            "session_id": session_id,
            "task_id": omni_message.task_id,
        }
        if omni_message.content:
            event["content"] = omni_message.content
        if omni_message.card_schema:
            event["card_schema"] = omni_message.card_schema

        await sse_push(session_id, event)

    async def _write_offline_inbox(
        self,
        session_id: str,
        omni_message: OmniMessage,
        channel_type: str,
    ) -> None:
        """将消息写入离线信箱（用户离线时）。"""
        # 获取 user_id（通过 session_id 查询）
        from mao.db.models.session import MaoSession
        sess_result = await self.db.execute(
            select(MaoSession).where(MaoSession.session_id == session_id)
        )
        session = sess_result.scalar_one_or_none()
        if not session:
            return

        inbox = MaoOfflineInbox(
            user_id=session.user_id,
            session_id=session_id,
            task_id=omni_message.task_id,
            channel_type=channel_type,
            message_type=omni_message.message_type,
            message_content=omni_message.content,
            card_schema=omni_message.card_schema,
        )
        self.db.add(inbox)
        await self.db.flush()
        logger.info(f"Message written to offline inbox for user {session.user_id}")
