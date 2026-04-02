"""SOP 画布工作流 ORM 模型 — mao_workflow / mao_workflow_snapshot"""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mao.db.database import Base


class MaoWorkflow(Base):
    __tablename__ = "mao_workflow"
    __table_args__ = (
        Index("ix_mao_workflow_updated_at", "updated_at"),
        Index("ix_mao_workflow_created_at", "created_at"),
        {"comment": "SOP 画布工作流表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    workflow_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="工作流唯一标识 wf_{uuid}")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="工作流名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="工作流描述（供 Router 匹配）")
    dag_definition: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="DAG 结构定义（节点列表 + 边列表），最大 65KB，超大 DAG 应拆分节点表",
    )
    published_version: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="当前已发布版本号")
    is_draft: Mapped[bool] = mapped_column(nullable=False, default=True, comment="是否草稿状态")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, comment="是否启用")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, comment="创建者 user_id")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )

    snapshots: Mapped[list["MaoWorkflowSnapshot"]] = relationship(back_populates="workflow")


class MaoWorkflowSnapshot(Base):
    """Workflow 发布快照表 — 不可变，用于版本溯源与回滚。"""

    __tablename__ = "mao_workflow_snapshot"
    __table_args__ = (
        Index("ix_mao_workflow_snapshot_updated_at", "updated_at"),
        Index("ix_mao_workflow_snapshot_created_at", "created_at"),
        {"comment": "Workflow 发布快照表（不可变）"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    workflow_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("mao_workflow.workflow_id"),
        nullable=False,
        index=True,
        comment="所属 Workflow",
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False, comment="版本号（如 v1.0）")
    snapshot_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, comment="完整 Workflow 快照")
    published_by: Mapped[str] = mapped_column(String(64), nullable=False, comment="发布者 user_id")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )

    workflow: Mapped["MaoWorkflow"] = relationship(back_populates="snapshots")
