"""
Kafka 生产者与消费者管理
Observer Log 模式：所有 Thought/Action/Card 在发出瞬间异步投入 Kafka，
不依赖执行引擎状态落盘，彻底消除引擎崩溃导致的状态丢失风险。
"""
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from mao.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 全局生产者单例（应用启动时初始化）
_producer: AIOKafkaProducer | None = None


async def get_producer() -> AIOKafkaProducer:
    """获取全局 Kafka 生产者（懒初始化）。"""
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            acks="all",           # 等待所有副本确认，保证不丢消息
            enable_idempotence=True,  # 幂等生产者，防止重复消息
            compression_type="gzip",
        )
        await _producer.start()
    return _producer


async def stop_producer() -> None:
    """应用关闭时优雅停止生产者。"""
    global _producer
    if _producer:
        await _producer.stop()
        _producer = None


# ── 审计事件发送 ──────────────────────────────────────────────────────────────

async def emit_thought(task_id: str, step_seq: int, thought: str, token_usage: dict[str, Any]) -> None:
    """Observer Log：发送 Thought 审计事件。"""
    producer = await get_producer()
    await producer.send_and_wait(
        settings.kafka_topic_audit_thought,
        value={
            "task_id": task_id,
            "step_seq": step_seq,
            "thought": thought,
            "token_usage": token_usage,
        },
        key=task_id.encode(),
    )


async def emit_action(
    task_id: str,
    step_seq: int,
    tool_name: str,
    tool_input: dict[str, Any],
    tool_output: dict[str, Any] | None = None,
    latency_ms: int = 0,
) -> None:
    """Observer Log：发送 Action/Observation 审计事件。"""
    producer = await get_producer()
    await producer.send_and_wait(
        settings.kafka_topic_audit_action,
        value={
            "task_id": task_id,
            "step_seq": step_seq,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_output": tool_output,
            "latency_ms": latency_ms,
        },
        key=task_id.encode(),
    )


async def emit_card(task_id: str, session_id: str, card_schema: dict[str, Any]) -> None:
    """Observer Log：发送卡片下发审计事件。"""
    producer = await get_producer()
    await producer.send_and_wait(
        settings.kafka_topic_audit_card_emit,
        value={
            "task_id": task_id,
            "session_id": session_id,
            "card_schema": card_schema,
        },
        key=task_id.encode(),
    )


async def emit_callback(source_system: str, event_type: str, payload: dict[str, Any]) -> None:
    """Observer Log：发送外部回调事件。"""
    producer = await get_producer()
    await producer.send_and_wait(
        settings.kafka_topic_audit_callback,
        value={
            "source_system": source_system,
            "event_type": event_type,
            "payload": payload,
        },
    )


# ── 消费者工厂 ────────────────────────────────────────────────────────────────

def create_consumer(topics: list[str], group_id: str | None = None) -> AIOKafkaConsumer:
    """
    创建 Kafka 消费者。
    每个独立服务（Archiver、InboxRetry）应创建自己的消费者实例。
    """
    return AIOKafkaConsumer(
        *topics,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=group_id or settings.kafka_group_id,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,  # 手动提交，确保幂等消费
    )


async def consume_messages(
    topics: list[str],
    group_id: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    异步生成器：消费指定 Topic 的消息，手动提交 offset。
    用法：
        async for msg in consume_messages(["mao.audit.thought"], "archiver"):
            process(msg)
    """
    consumer = create_consumer(topics, group_id)
    await consumer.start()
    try:
        async for msg in consumer:
            yield msg.value
            await consumer.commit()
    finally:
        await consumer.stop()
