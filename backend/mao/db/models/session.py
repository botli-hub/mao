"""会话表 ORM 模型 — mao_session"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mao.db.database import Base


class MaoSession(Base):
    __tablename__ = "mao_session"
    __table_args__ = {"comment": "用户会话表"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="会话唯一标识 sess_{uuid}")
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("mao_user.user_id"), nullable=False, index=True, comment="所属用户")
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False, default="WEB", comment="渠道类型: WEB/FEISHU/DINGTALK/WECOM")
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="新会话", comment="会话标题")
    context_window: Mapped[int] = mapped_column(Integer, nullable=False, default=20, comment="滑动窗口大小（消息条数）")
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="消息总数")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )

    # 关联
    user: Mapped["MaoUser"] = relationship(back_populates="sessions")  # type: ignore[name-defined]
    messages: Mapped[list["MaoMessage"]] = relationship(back_populates="session", order_by="MaoMessage.id")
    tasks: Mapped[list["MaoTask"]] = relationship(back_populates="session")  # type: ignore[name-defined]
