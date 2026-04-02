"""
离线信箱主动重投服务（Inbox Retrier）
实现指数退避重试（Exponential Backoff）机制。
对于飞书等渠道，用户离线后机器人调用失败，系统自动退避重试直到用户上线或达到最大次数。
退避策略：1min → 5min → 15min → 死信队列
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.channel.dispatcher import ChannelDispatcher
from mao.channel.base import OmniMessage
from mao.db.database import AsyncSessionLocal
from mao.db.models.task import MaoOfflineInbox

logger = logging.getLogger(__name__)

# 退避间隔（秒）：第 1 次 1 分钟，第 2 次 5 分钟，第 3 次 15 分钟
BACKOFF_INTERVALS = [60, 300, 900]
MAX_RETRY_COUNT = len(BACKOFF_INTERVALS)


class InboxRetrier:
    """
    离线信箱重投服务。
    定时扫描 mao_offline_inbox 表，对未读且可重试的消息执行退避重投。
    """

    def __init__(self) -> None:
        self._running = False

    async def start(self) -> None:
        """启动重投服务（每分钟扫描一次）。"""
        self._running = True
        logger.info("Inbox retrier service started")
        while self._running:
            await asyncio.sleep(60)  # 每分钟扫描一次
            try:
                await self._retry_pending_messages()
            except Exception as e:
                logger.error(f"Inbox retry scan error: {e}")

    async def stop(self) -> None:
        """停止重投服务。"""
        self._running = False

    async def _retry_pending_messages(self) -> None:
        """扫描并重投到期的离线消息。"""
        async with AsyncSessionLocal() as db:
            now = datetime.utcnow()

            # 查找需要重试的消息：未读 + 未超过最大重试次数 + 上次重试时间已过退避间隔
            result = await db.execute(
                select(MaoOfflineInbox).where(
                    MaoOfflineInbox.is_read == False,  # noqa: E712
                    MaoOfflineInbox.retry_count < MAX_RETRY_COUNT,
                )
            )
            inbox_items = result.scalars().all()

            for item in inbox_items:
                if not self._is_retry_due(item, now):
                    continue

                await self._attempt_retry(item, db, now)

            await db.commit()

    def _is_retry_due(self, item: MaoOfflineInbox, now: datetime) -> bool:
        """判断该消息是否到了重试时机。"""
        retry_count = item.retry_count or 0
        if retry_count == 0:
            # 首次重试：距创建时间超过 1 分钟
            return (now - item.created_at).total_seconds() >= BACKOFF_INTERVALS[0]

        if item.last_retry_at is None:
            return True

        # 按退避间隔判断
        interval_index = min(retry_count, len(BACKOFF_INTERVALS) - 1)
        interval = BACKOFF_INTERVALS[interval_index]
        return (now - item.last_retry_at).total_seconds() >= interval

    async def _attempt_retry(
        self,
        item: MaoOfflineInbox,
        db: AsyncSession,
        now: datetime,
    ) -> None:
        """尝试重投单条离线消息。"""
        retry_count = (item.retry_count or 0) + 1
        logger.info(
            f"Retrying offline inbox item {item.id} "
            f"(attempt {retry_count}/{MAX_RETRY_COUNT}, channel={item.channel_type})"
        )

        try:
            # 构建 OmniMessage
            omni_msg = OmniMessage(
                session_id=item.session_id,
                message_type=item.message_type,
                content=item.message_content,
                card_schema=item.card_schema,
                task_id=item.task_id,
            )

            # 尝试通过渠道适配器发送
            dispatcher = ChannelDispatcher(db)
            await dispatcher.dispatch(item.session_id, omni_msg)

            # 发送成功：标记为已读
            item.is_read = True
            item.retry_count = retry_count
            item.last_retry_at = now
            db.add(item)
            logger.info(f"Offline inbox item {item.id} delivered successfully on retry {retry_count}")

        except Exception as e:
            logger.warning(f"Retry {retry_count} failed for inbox item {item.id}: {e}")

            # 更新重试计数
            item.retry_count = retry_count
            item.last_retry_at = now
            db.add(item)

            # 达到最大重试次数：转入死信队列
            if retry_count >= MAX_RETRY_COUNT:
                await self._send_to_dead_letter(item, str(e), db)

    async def _send_to_dead_letter(
        self,
        item: MaoOfflineInbox,
        last_error: str,
        db: AsyncSession,
    ) -> None:
        """
        将消息转入死信队列（发送 Kafka 告警事件）。
        运营人员可通过监控大盘查看死信消息并手动处理。
        """
        logger.error(
            f"Offline inbox item {item.id} moved to dead letter queue "
            f"after {MAX_RETRY_COUNT} retries. Last error: {last_error}"
        )
        try:
            from mao.core.kafka_client import get_producer
            producer = await get_producer()
            await producer.send_and_wait(
                "mao.dead_letter.inbox",
                value={
                    "inbox_id": item.id,
                    "user_id": item.user_id,
                    "session_id": item.session_id,
                    "task_id": item.task_id,
                    "channel_type": item.channel_type,
                    "message_type": item.message_type,
                    "retry_count": item.retry_count,
                    "last_error": last_error,
                },
            )
        except Exception as e:
            logger.error(f"Failed to send dead letter event: {e}")


# 全局重投服务单例
_retrier: InboxRetrier | None = None


def get_inbox_retrier() -> InboxRetrier:
    """获取重投服务单例。"""
    global _retrier
    if _retrier is None:
        _retrier = InboxRetrier()
    return _retrier
