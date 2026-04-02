"""
归档服务（Archiver）
消费 Kafka task_log 事件，将 Redis 中间态数据批量同步到 MySQL。
实现热冷数据一致性保障体系中的"异步流式归档"策略。
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.core.kafka_client import get_consumer
from mao.core.redis_client import redis_client, state_get_steps
from mao.db.database import AsyncSessionLocal
from mao.db.models.task import MaoTask, MaoTaskLog, MaoTaskSnapshotArchive

logger = logging.getLogger(__name__)

# Kafka Topic 定义
TOPIC_TASK_LOG = "mao.task.log"
TOPIC_TASK_STATUS = "mao.task.status"
TOPIC_OBSERVER_LOG = "mao.observer.log"


class ArchiverService:
    """
    归档服务。
    负责：
    1. 消费 Kafka task_log 事件，幂等写入 MySQL mao_task_log
    2. 扫描 Redis Key TTL 预警，触发深冻结归档
    3. 任务完成后归档完整执行链路
    """

    def __init__(self) -> None:
        self._running = False

    async def start(self) -> None:
        """启动归档服务（后台运行）。"""
        self._running = True
        logger.info("Archiver service started")
        await asyncio.gather(
            self._consume_task_logs(),
            self._scan_ttl_warnings(),
        )

    async def stop(self) -> None:
        """停止归档服务。"""
        self._running = False
        logger.info("Archiver service stopped")

    async def _consume_task_logs(self) -> None:
        """
        消费 Kafka task_log 事件，幂等写入 MySQL mao_task_log。
        幂等键：task_id + step_index，防止重复消费。
        """
        consumer = await get_consumer(
            topics=[TOPIC_TASK_LOG, TOPIC_OBSERVER_LOG],
            group_id="mao-archiver",
        )
        try:
            async for msg in consumer:
                if not self._running:
                    break
                try:
                    event = json.loads(msg.value)
                    await self._archive_task_log(event)
                except Exception as e:
                    logger.error(f"Failed to archive task log: {e}, msg={msg.value}")
        finally:
            await consumer.stop()

    async def _archive_task_log(self, event: dict[str, Any]) -> None:
        """将单条 task_log 事件幂等写入 MySQL。"""
        task_id = event.get("task_id")
        step_index = event.get("step_index")
        if not task_id or step_index is None:
            return

        async with AsyncSessionLocal() as db:
            # 幂等检查：同一 task_id + step_index 只写一次
            existing = await db.execute(
                select(MaoTaskLog).where(
                    MaoTaskLog.task_id == task_id,
                    MaoTaskLog.step_index == step_index,
                )
            )
            if existing.scalar_one_or_none():
                return  # 已存在，跳过

            log = MaoTaskLog(
                task_id=task_id,
                step_index=step_index,
                step_type=event.get("step_type", "UNKNOWN"),
                content=event.get("content"),
                skill_id=event.get("skill_id"),
                state_digest=event.get("state_digest"),
                execution_version=event.get("execution_version"),
            )
            db.add(log)
            await db.commit()
            logger.debug(f"Archived task log: {task_id} step {step_index}")

    async def _scan_ttl_warnings(self) -> None:
        """
        定时扫描 Redis Key TTL 预警（每 15 分钟）。
        当 TTL 剩余不足 10% 时，触发深冻结归档。
        """
        while self._running:
            await asyncio.sleep(900)  # 15 分钟
            try:
                await self._check_expiring_keys()
            except Exception as e:
                logger.error(f"TTL scan error: {e}")

    async def _check_expiring_keys(self) -> None:
        """扫描即将过期的 StateDB Key 并触发归档。"""
        # 扫描所有 task state keys
        cursor = 0
        pattern = "mao:state:*:steps"
        while True:
            cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                ttl = await redis_client.ttl(key_str)
                if ttl < 0:
                    continue  # 无过期时间，跳过

                # 获取原始 TTL（从 key 对应的 meta key 中读取）
                task_id = key_str.split(":")[2]
                meta_key = f"mao:state:{task_id}:meta"
                meta = await redis_client.hgetall(meta_key)
                if meta:
                    original_ttl = int(meta.get(b"ttl", 3600))
                    # TTL 剩余不足 10%，触发归档
                    if ttl < original_ttl * 0.1:
                        logger.warning(f"Task {task_id} StateDB TTL warning: {ttl}s remaining")
                        await self._deep_freeze_archive(task_id)

            if cursor == 0:
                break

    async def _deep_freeze_archive(self, task_id: str) -> None:
        """
        深冻结归档：将 Redis 完整快照序列化到 MySQL mao_task_snapshot_archive。
        触发条件：任务 SUSPEND 或 Redis TTL 预警。
        """
        async with AsyncSessionLocal() as db:
            # 检查是否已归档
            existing = await db.execute(
                select(MaoTaskSnapshotArchive).where(
                    MaoTaskSnapshotArchive.task_id == task_id,
                    MaoTaskSnapshotArchive.trigger_type == "TTL_WARNING",
                )
            )
            if existing.scalar_one_or_none():
                return  # 已归档，跳过

            # 从 Redis 读取完整快照
            steps = await state_get_steps(task_id)
            if not steps:
                return

            # 读取黑板数据
            from mao.engine.react.blackboard import Blackboard
            blackboard = await Blackboard.load(task_id)

            # 计算当前挂起轮次
            from sqlalchemy import func
            count_result = await db.execute(
                select(func.count()).where(MaoTaskSnapshotArchive.task_id == task_id)
            )
            suspend_seq = (count_result.scalar() or 0) + 1

            archive = MaoTaskSnapshotArchive(
                task_id=task_id,
                suspend_seq=suspend_seq,
                trigger_type="TTL_WARNING",
                snapshot_data={"steps": steps},
                blackboard_data=blackboard.to_dict(),
                step_count=len(steps),
            )
            db.add(archive)
            await db.commit()
            logger.info(f"Deep freeze archive completed for task {task_id} (TTL warning)")


# 全局归档服务单例
_archiver: ArchiverService | None = None


def get_archiver() -> ArchiverService:
    """获取归档服务单例。"""
    global _archiver
    if _archiver is None:
        _archiver = ArchiverService()
    return _archiver
