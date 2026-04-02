"""
Redis 客户端管理
- DB 0：通用缓存（会话、锁等）
- DB 1：StateDB（任务执行快照，Append-only RPUSH）
"""
import json
from typing import Any

import redis.asyncio as aioredis

from mao.core.config import get_settings

settings = get_settings()

# DB 0 — 通用缓存
_cache_pool = aioredis.ConnectionPool.from_url(
    settings.redis_url, decode_responses=True, max_connections=50
)

# DB 1 — StateDB（任务快照）
_state_pool = aioredis.ConnectionPool.from_url(
    settings.redis_url.rstrip("0") + str(settings.redis_state_db),
    decode_responses=True,
    max_connections=50,
)


def get_cache_client() -> aioredis.Redis:
    """获取通用缓存客户端（DB 0）。"""
    return aioredis.Redis(connection_pool=_cache_pool)


def get_state_client() -> aioredis.Redis:
    """获取 StateDB 客户端（DB 1），用于任务快照 Append-only 写入。"""
    return aioredis.Redis(connection_pool=_state_pool)


# ── StateDB 操作封装 ──────────────────────────────────────────────────────────

async def state_append_step(task_id: str, step: dict[str, Any]) -> int:
    """
    向 StateDB 追加一个推演步骤（Append-only RPUSH）。
    返回当前列表长度（即步骤总数）。
    """
    client = get_state_client()
    key = f"task:steps:{task_id}"
    length = await client.rpush(key, json.dumps(step, ensure_ascii=False))
    # 刷新 TTL
    await client.expire(key, settings.redis_task_snapshot_ttl)
    return int(length)


async def state_get_steps(task_id: str) -> list[dict[str, Any]]:
    """获取任务的全部推演步骤列表。"""
    client = get_state_client()
    key = f"task:steps:{task_id}"
    raw_list = await client.lrange(key, 0, -1)
    return [json.loads(item) for item in raw_list]


async def state_set_blackboard(task_id: str, blackboard: dict[str, Any]) -> None:
    """写入/更新任务黑板（全量覆盖）。"""
    client = get_state_client()
    key = f"task:blackboard:{task_id}"
    await client.set(key, json.dumps(blackboard, ensure_ascii=False))
    await client.expire(key, settings.redis_task_snapshot_ttl)


async def state_get_blackboard(task_id: str) -> dict[str, Any]:
    """读取任务黑板，若不存在则返回空字典。"""
    client = get_state_client()
    key = f"task:blackboard:{task_id}"
    raw = await client.get(key)
    return json.loads(raw) if raw else {}


async def state_delete(task_id: str) -> None:
    """任务完成后清理 StateDB 中的快照数据。"""
    client = get_state_client()
    await client.delete(f"task:steps:{task_id}", f"task:blackboard:{task_id}")


async def state_ttl_remaining(task_id: str) -> int:
    """获取任务步骤列表的剩余 TTL（秒），-2 表示不存在，-1 表示永不过期。"""
    client = get_state_client()
    return int(await client.ttl(f"task:steps:{task_id}"))


# ── 分布式锁 ──────────────────────────────────────────────────────────────────

async def acquire_lock(lock_key: str, ttl: int = 30) -> bool:
    """
    尝试获取分布式锁（SET NX EX）。
    返回 True 表示成功获取，False 表示锁已被占用。
    """
    client = get_cache_client()
    result = await client.set(f"lock:{lock_key}", "1", nx=True, ex=ttl)
    return result is True


async def release_lock(lock_key: str) -> None:
    """释放分布式锁。"""
    client = get_cache_client()
    await client.delete(f"lock:{lock_key}")


# ── SSE 推送队列 ──────────────────────────────────────────────────────────────

async def sse_push(session_id: str, event: dict[str, Any]) -> None:
    """
    将 SSE 事件推入用户会话的推送队列（List）。
    SSE 处理器通过 BLPOP 消费。
    """
    client = get_cache_client()
    key = f"sse:queue:{session_id}"
    await client.rpush(key, json.dumps(event, ensure_ascii=False))
    await client.expire(key, 3600)  # 1h TTL


async def sse_pop(session_id: str, timeout: int = 30) -> dict[str, Any] | None:
    """
    从 SSE 队列阻塞弹出一个事件（BLPOP）。
    timeout 秒后无事件则返回 None。
    """
    client = get_cache_client()
    key = f"sse:queue:{session_id}"
    result = await client.blpop(key, timeout=timeout)
    if result:
        _, raw = result
        return json.loads(raw)
    return None
