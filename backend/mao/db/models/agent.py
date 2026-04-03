"""智能体相关 ORM 模型 — mao_agent / mao_agent_skill_rel / mao_agent_snapshot"""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mao.db.database import Base


class MaoAgent(Base):
    __tablename__ = "mao_agent"
    __table_args__ = (
        Index("ix_mao_agent_updated_at", "updated_at"),
        Index("ix_mao_agent_created_at", "created_at"),
        {"comment": "智能体定义表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    agent_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="Agent 唯一标识 agent_{uuid}")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="Agent 名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Agent 职责描述（供 Router 匹配）")
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True, comment="系统提示词（定义 Agent 人设与行为边界）")
    model_config_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True,
        comment="模型配置: {provider, model, temperature, max_steps, max_tokens}"
    )
    rag_retrieval_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True,
        comment="RAG 检索配置: {knowledge_base_id, top_k, similarity_threshold}"
    )
    published_version: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="当前已发布版本号（不可变快照）")
    is_draft: Mapped[bool] = mapped_column(nullable=False, default=True, comment="是否草稿状态（草稿不可被 Router 调用）")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, comment="是否启用")
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("mao_user.user_id"), nullable=False, comment="创建者 user_id")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )

    @hybrid_property
    def model_config(self) -> dict[str, Any]:
        return self.model_config_data or {}

    @model_config.setter
    def model_config(self, value: dict[str, Any] | None) -> None:
        self.model_config_data = value or {}

    @hybrid_property
    def current_version(self) -> str | None:
        return self.published_version

    @current_version.setter
    def current_version(self, value: str | None) -> None:
        self.published_version = value

    @hybrid_property
    def max_steps(self) -> int:
        return int((self.model_config_data or {}).get("max_steps", 10))

    @max_steps.setter
    def max_steps(self, value: int) -> None:
        cfg = dict(self.model_config_data or {})
        cfg["max_steps"] = value
        self.model_config_data = cfg

    @hybrid_property
    def rag_kb_ids(self) -> list[str]:
        cfg = self.rag_retrieval_config or {}
        kb_ids = cfg.get("rag_kb_ids")
        if isinstance(kb_ids, list):
            return [str(v) for v in kb_ids]
        knowledge_base_id = cfg.get("knowledge_base_id")
        return [str(knowledge_base_id)] if knowledge_base_id else []

    @rag_kb_ids.setter
    def rag_kb_ids(self, value: list[str]) -> None:
        cfg = dict(self.rag_retrieval_config or {})
        cfg["rag_kb_ids"] = value
        self.rag_retrieval_config = cfg

    # 关联
    creator: Mapped["MaoUser"] = relationship(back_populates="agents")  # type: ignore[name-defined]
    skill_rels: Mapped[list["MaoAgentSkillRel"]] = relationship(back_populates="agent")
    snapshots: Mapped[list["MaoAgentSnapshot"]] = relationship(back_populates="agent")


class MaoAgentSkillRel(Base):
    """Agent 与技能的多对多关联表。"""
    __tablename__ = "mao_agent_skill_rel"
    __table_args__ = (
        Index("ix_mao_agent_skill_rel_updated_at", "updated_at"),
        Index("ix_mao_agent_skill_rel_created_at", "created_at"),
        {"comment": "Agent 与技能关联表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    agent_id: Mapped[str] = mapped_column(String(64), ForeignKey("mao_agent.agent_id"), nullable=False, index=True, comment="Agent ID")
    skill_id: Mapped[str] = mapped_column(String(64), ForeignKey("mao_skill.skill_id"), nullable=False, index=True, comment="技能 ID")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序权重")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )

    # 关联
    agent: Mapped["MaoAgent"] = relationship(back_populates="skill_rels")
    skill: Mapped["MaoSkill"] = relationship()  # type: ignore[name-defined]


class MaoAgentSnapshot(Base):
    """Agent 发布快照表 — 不可变，用于版本溯源与回滚。"""
    __tablename__ = "mao_agent_snapshot"
    __table_args__ = (
        Index("ix_mao_agent_snapshot_updated_at", "updated_at"),
        Index("ix_mao_agent_snapshot_created_at", "created_at"),
        {"comment": "Agent 发布快照表（不可变）"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    agent_id: Mapped[str] = mapped_column(String(64), ForeignKey("mao_agent.agent_id"), nullable=False, index=True, comment="所属 Agent")
    version: Mapped[str] = mapped_column(String(32), nullable=False, comment="版本号（如 v1.0）")
    snapshot_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, comment="完整 Agent 配置快照（含技能列表）")
    published_by: Mapped[str] = mapped_column(String(64), nullable=False, comment="发布者 user_id")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )

    # 关联
    agent: Mapped["MaoAgent"] = relationship(back_populates="snapshots")
