"""消息表 ORM 模型 — mao_message

内外部记忆隔离规则：
  本表仅存储用户会话的对话历史（Session Memory）。
  L4 执行面的 Thought/Action/Observation 严禁写入本表。
  当且仅当任务结束或需要人类介入时，由 Worker 生成
  TASK_SUMMARY 或 CARD 写入本表。
"""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mao.db.database import Base


class MaoMessage(Base):
    __tablename__ = "mao_message"
    __table_args__ = {"comment": "会话消息表（Session Memory，严禁写入 Thought/Action/Observation）"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="消息主键")
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("mao_session.session_id"), nullable=False, index=True, comment="所属会话")
    role: Mapped[str] = mapped_column(String(16), nullable=False, comment="角色: user/assistant/system")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="文本内容")
    message_type: Mapped[str] = mapped_column(String(32), nullable=False, default="TEXT", comment="类型: TEXT/CARD/TASK_SUMMARY/SYSTEM_NOTICE/SUSPEND_CARD")
    card_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="卡片 JSON Schema（message_type=CARD 时）")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )

    # 关联
    session: Mapped["MaoSession"] = relationship(back_populates="messages")  # type: ignore[name-defined]
