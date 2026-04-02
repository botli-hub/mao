"""任务相关 ORM 模型 — mao_task / mao_task_log / mao_task_snapshot_archive"""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mao.db.database import Base


class MaoTask(Base):
    __tablename__ = "mao_task"
    __table_args__ = (
        Index("ix_mao_task_updated_at", "updated_at"),
        Index("ix_mao_task_created_at", "created_at"),
        Index("ix_mao_task_status", "status"),
        {"comment": "任务表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    task_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="任务唯一标识 task_{ulid}")
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("mao_session.session_id"), nullable=False, index=True, comment="所属会话")
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, comment="承接的 Agent（与 workflow_id 二选一）")
    workflow_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, comment="承接的 SOP 画布（与 agent_id 二选一）")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", comment="任务状态（见 TaskStatus 枚举）")
    state_snap_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True, comment="StateDB 外置快照 Key，实际快照存于 Redis，严禁存入本表")
    execution_version: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="执行时绑定的 SOP 版本号")
    oa_ticket_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="关联的 OA 审批单号")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, comment="幂等键: {task_id}_{card_action_id}")
    suspend_reason: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="挂起原因描述")
    callback_expect: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="期望的回调事件类型")
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="失败时的错误信息")
    expired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="任务过期时间（TTL 强杀）")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )

    # 关联
    session: Mapped["MaoSession"] = relationship(back_populates="tasks")  # type: ignore[name-defined]
    logs: Mapped[list["MaoTaskLog"]] = relationship(back_populates="task", order_by="MaoTaskLog.id")
    snapshots: Mapped[list["MaoTaskSnapshotArchive"]] = relationship(back_populates="task")


class MaoTaskLog(Base):
    """任务执行日志（Task Scratchpad）— 仅供审计，严禁将此表数据直接展示给 C 端用户。"""
    __tablename__ = "mao_task_log"
    __table_args__ = (
        Index("ix_mao_task_log_updated_at", "updated_at"),
        Index("ix_mao_task_log_created_at", "created_at"),
        {"comment": "任务执行日志表（Task Scratchpad，仅供审计）"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="日志主键")
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("mao_task.task_id"), nullable=False, index=True, comment="所属任务")
    step_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="步骤序号（从 1 开始）")
    step_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="步骤类型: ROUTER/THOUGHT/ACTION/OBSERVATION/FINAL_ANSWER")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="步骤内容（Thought 文本 / Action JSON / Observation 结果）")
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="调用的工具名称（step_type=ACTION 时）")
    tool_input: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="工具调用输入参数")
    tool_output: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="工具调用输出结果")
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="Token 消耗: {prompt, completion, total}")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="本步骤耗时（毫秒）")
    state_digest: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True,
        comment="关键状态摘要（Shadow Sync）: {blackboard_snapshot, execution_version, token_usage}"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )

    # 关联
    task: Mapped["MaoTask"] = relationship(back_populates="logs")


class MaoTaskSnapshotArchive(Base):
    """任务快照归档表 — 深冻结归档，支持多轮挂起。"""
    __tablename__ = "mao_task_snapshot_archive"
    __table_args__ = (
        Index("ix_mao_task_snapshot_archive_updated_at", "updated_at"),
        Index("ix_mao_task_snapshot_archive_created_at", "created_at"),
        {"comment": "任务快照归档表（深冻结，支持多轮挂起）"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("mao_task.task_id"), nullable=False, index=True, comment="所属任务")
    suspend_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="挂起轮次（支持多轮挂起，从 1 开始）")
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="归档触发方式: SUSPEND_EVENT/TTL_WARNING/CRON_SCAN")
    snapshot_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="完整快照数据（从 Redis 序列化）")
    blackboard_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="黑板数据快照")
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="归档时的推演步数")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )

    # 关联
    task: Mapped["MaoTask"] = relationship(back_populates="snapshots")
