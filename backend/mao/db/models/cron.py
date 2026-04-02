"""定时调度任务 ORM 模型 — mao_cron_job"""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from mao.db.database import Base


class MaoCronJob(Base):
    __tablename__ = "mao_cron_job"
    __table_args__ = (
        Index("ix_mao_cron_job_updated_at", "updated_at"),
        Index("ix_mao_cron_job_created_at", "created_at"),
        Index("ix_mao_cron_job_status", "status"),
        {"comment": "定时调度任务表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="调度任务唯一标识 cron_{uuid}")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="任务名称")
    description: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="任务描述")
    cron_expr: Mapped[str] = mapped_column(String(64), nullable=False, comment="Cron 表达式（6 字段格式）")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai", comment="时区（必填，防云原生时区漂移）")
    trigger_message: Mapped[str] = mapped_column(String(512), nullable=False, comment="触发时发送的自然语言指令")
    target_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="目标会话 ID")
    target_user_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="执行身份的 user_id")
    overlap_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="SKIP", comment="重叠策略: SKIP/QUEUE/CONCURRENT")
    auth_impersonation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="权限代理配置（服务账号委托）")
    retry_policy: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="重试策略: {max_retries, backoff_seconds}")
    fallback_action: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="降级通知配置")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", comment="状态: ACTIVE/PAUSED/DISABLED")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="上次执行时间")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="下次执行时间")
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="累计执行次数")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, comment="创建者 user_id")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )
