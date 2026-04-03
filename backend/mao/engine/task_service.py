"""
任务服务（Task Service）
协调 ReAct Runner 的生命周期：创建、启动、挂起、恢复、终止。
负责将执行结果写入 MySQL（mao_task / mao_task_log）。
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.core.enums import MessageType, TaskStatus
from mao.core.kafka_client import emit_card
from mao.core.redis_client import (
    acquire_lock,
    release_lock,
    sse_push,
    state_append_step,
    state_delete,
    state_get_steps,
)
from mao.db.models.message import MaoMessage
from mao.db.models.session import MaoSession
from mao.db.models.task import MaoTask, MaoTaskLog, MaoTaskSnapshotArchive
from mao.engine.react.blackboard import Blackboard
from mao.engine.react.runner import (
    CircuitBreakerTripped,
    MaxStepsExceeded,
    ReActRunner,
)
from mao.engine.react.state_machine import InvalidTransitionError, validate_transition

logger = logging.getLogger(__name__)


class TaskService:
    """
    任务服务：管理任务的完整生命周期。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_task(
        self,
        session_id: str,
        agent_id: str | None = None,
        workflow_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> MaoTask:
        """创建新任务（PENDING 状态）。"""
        import ulid
        task_id = f"task_{ulid.new()}"
        task = MaoTask(
            task_id=task_id,
            session_id=session_id,
            agent_id=agent_id,
            workflow_id=workflow_id,
            status=TaskStatus.PENDING.value,
            idempotency_key=idempotency_key,
        )
        self.db.add(task)
        await self.db.flush()
        return task

    async def run_task(
        self,
        task: MaoTask,
        user_message: str,
        agent_config: dict[str, Any],
        skill_registry: dict[str, dict[str, Any]],
    ) -> None:
        """
        在后台异步执行任务推演。
        此方法应通过 asyncio.create_task() 在后台运行，不阻塞 API 响应。
        """
        task_id = task.task_id
        session_id = task.session_id

        # 获取分布式锁，防止同一任务被多个 Worker 并发执行
        lock_key = f"task_run:{task_id}"
        if not await acquire_lock(lock_key, ttl=300):
            logger.warning(f"[{task_id}] Failed to acquire lock, task may be running on another worker")
            return

        try:
            # 事务级悲观锁：确保同一 task 的状态流转在数据库层串行化
            locked_task_result = await self.db.execute(
                select(MaoTask).where(MaoTask.task_id == task_id).with_for_update()
            )
            locked_task = locked_task_result.scalar_one_or_none()
            if not locked_task:
                logger.warning(f"[{task_id}] Task row not found when acquiring DB lock")
                return
            task = locked_task

            # 更新状态：PENDING → RUNNING
            await self._transition_status(task, TaskStatus.RUNNING)

            # 推送 SSE 事件：任务开始
            await sse_push(session_id, {"event": "task_start", "task_id": task_id})

            # 加载或初始化黑板
            blackboard = await Blackboard.load(task_id)

            # 计算断点续传偏移量（若任务之前已执行过部分步骤）
            existing_steps = await state_get_steps(task_id)
            step_offset = len(existing_steps)

            # 实例化 ReAct Runner 并执行
            runner = ReActRunner(
                task_id=task_id,
                agent_config=agent_config,
                skill_registry=skill_registry,
            )

            result = await runner.run(
                user_message=user_message,
                blackboard=blackboard,
                history_messages=await self._build_history_messages(task.session_id),
                step_offset=step_offset,
            )

            # 处理执行结果
            status = result.get("status")

            if status == TaskStatus.COMPLETED.value or status == TaskStatus.COMPLETED:
                await self._on_completed(task, result, session_id)

            elif status == TaskStatus.SUSPENDED.value or status == TaskStatus.SUSPENDED:
                await self._on_suspended(task, result)

            elif status == "CARD_EMITTED":
                await self._on_card_emitted(task, result, session_id)

        except (CircuitBreakerTripped, MaxStepsExceeded) as e:
            logger.error(f"[{task_id}] Engine halted: {e}")
            await self._transition_status(task, TaskStatus.FAILED, error_message=str(e))
            await sse_push(session_id, {"event": "task_failed", "task_id": task_id, "error": str(e)})

        except Exception as e:
            logger.exception(f"[{task_id}] Unexpected error: {e}")
            await self._transition_status(task, TaskStatus.FAILED, error_message=str(e))
            await sse_push(session_id, {"event": "task_failed", "task_id": task_id, "error": str(e)})

        finally:
            await release_lock(lock_key)
            await self.db.commit()

    async def resume_task(
        self,
        task: MaoTask,
        callback_payload: dict[str, Any],
        agent_config: dict[str, Any],
        skill_registry: dict[str, dict[str, Any]],
    ) -> None:
        """
        从挂起状态恢复任务（回调唤醒）。
        将回调 payload 注入黑板，然后继续推演。
        """
        task_id = task.task_id

        # 将回调结果写入黑板
        blackboard = await Blackboard.load(task_id)
        blackboard.set("__callback_result__", callback_payload)
        await blackboard.save()

        # 更新状态：SUSPENDED → RUNNING
        await self._transition_status(task, TaskStatus.RUNNING)

        # 继续推演（传入回调结果作为新的用户消息）
        callback_message = f"[系统回调] 外部事件已返回：{callback_payload}"
        asyncio.create_task(
            self.run_task(task, callback_message, agent_config, skill_registry)
        )

    async def kill_task(self, task: MaoTask, reason: str = "Forced kill by admin") -> None:
        """强制终止任务（管理员熔断）。"""
        await self._transition_status(task, TaskStatus.CANCELLED, error_message=reason)
        await state_delete(task.task_id)
        await release_lock(f"task_run:{task.task_id}")
        await self.db.commit()

    async def _on_completed(
        self, task: MaoTask, result: dict[str, Any], session_id: str
    ) -> None:
        """任务完成处理：写入 TASK_SUMMARY 消息，归档 StateDB，推送 SSE。"""
        final_answer = result.get("final_answer", "任务已完成。")

        # 写入 TASK_SUMMARY 到 mao_message（Session Memory）
        # 注意：这是唯一允许写入 mao_message 的时机
        summary_msg = MaoMessage(
            session_id=session_id,
            role="assistant",
            content=final_answer,
            message_type=MessageType.TASK_SUMMARY.value,
        )
        self.db.add(summary_msg)

        # 更新任务状态
        await self._transition_status(task, TaskStatus.COMPLETED)

        # 清理 Redis StateDB（任务完成后释放内存）
        await state_delete(task.task_id)

        # 推送 SSE 事件
        await sse_push(session_id, {
            "event": "task_summary",
            "task_id": task.task_id,
            "content": final_answer,
        })

    async def _on_suspended(self, task: MaoTask, result: dict[str, Any]) -> None:
        """
        任务挂起处理：深冻结归档快照，更新任务状态。
        SUSPEND 时立即触发深冻结，不等待 30 分钟超时。
        """
        task_id = task.task_id
        callback_expect = result.get("callback_expect", "CALLBACK_RECEIVED")

        # 深冻结：从 Redis 读取完整快照并归档到 MySQL
        steps = await state_get_steps(task_id)
        blackboard = await Blackboard.load(task_id)

        # 计算当前挂起轮次
        from sqlalchemy import func
        suspend_count_result = await self.db.execute(
            select(func.count()).where(MaoTaskSnapshotArchive.task_id == task_id)
        )
        suspend_seq = (suspend_count_result.scalar() or 0) + 1

        archive = MaoTaskSnapshotArchive(
            task_id=task_id,
            suspend_seq=suspend_seq,
            trigger_type="SUSPEND_EVENT",
            snapshot_data={"steps": steps},
            blackboard_data=blackboard.to_dict(),
            step_count=len(steps),
        )
        self.db.add(archive)

        # 更新任务状态
        task.status = TaskStatus.SUSPENDED.value
        task.callback_expect = callback_expect
        task.suspend_reason = f"Waiting for: {callback_expect}"
        self.db.add(task)

    async def _on_card_emitted(
        self, task: MaoTask, result: dict[str, Any], session_id: str
    ) -> None:
        """
        卡片下发处理：写入 CARD 消息，推送 SSE，任务进入 SUSPENDED 等待用户交互。
        """
        card_schema = result.get("card_schema", {})
        task_id = task.task_id

        # 写入 CARD 到 mao_message（Session Memory）
        card_msg = MaoMessage(
            session_id=session_id,
            role="assistant",
            message_type=MessageType.CARD.value,
            card_schema=card_schema,
        )
        self.db.add(card_msg)

        # Observer Log：异步发送卡片审计事件
        asyncio.create_task(emit_card(task_id, session_id, card_schema))

        # 任务挂起，等待用户点击卡片
        task.status = TaskStatus.SUSPENDED.value
        task.suspend_reason = "Waiting for user card interaction"
        self.db.add(task)

        # 推送 SSE 事件
        await sse_push(session_id, {
            "event": "action_card",
            "task_id": task_id,
            "card_schema": card_schema,
        })

    async def _transition_status(
        self,
        task: MaoTask,
        target: TaskStatus,
        error_message: str | None = None,
    ) -> None:
        """验证并执行状态转换。"""
        current = TaskStatus(task.status)
        try:
            validate_transition(current, target)
        except InvalidTransitionError as e:
            logger.warning(f"[{task.task_id}] {e}")
            return

        task.status = target.value
        if error_message:
            task.error_message = error_message
        self.db.add(task)

    async def _build_history_messages(self, session_id: str) -> list[dict[str, str]]:
        """按会话窗口加载历史消息，作为 LLM 上下文输入。"""
        session_result = await self.db.execute(
            select(MaoSession).where(MaoSession.session_id == session_id)
        )
        session = session_result.scalar_one_or_none()
        context_window = session.context_window if session else 20

        result = await self.db.execute(
            select(MaoMessage)
            .where(MaoMessage.session_id == session_id)
            .order_by(MaoMessage.created_at.desc())
            .limit(max(context_window, 0))
        )
        rows = list(reversed(result.scalars().all()))

        history: list[dict[str, str]] = []
        for msg in rows:
            if msg.message_type == MessageType.CARD.value:
                continue
            content = msg.content or ""
            if not content.strip():
                continue
            role = msg.role if msg.role in {"user", "assistant", "system"} else "system"
            history.append({"role": role, "content": content})
        return history
