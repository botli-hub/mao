"""用户表 ORM 模型 — mao_user"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mao.db.database import Base


class MaoUser(Base):
    __tablename__ = "mao_user"
    __table_args__ = {"comment": "用户表"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="用户唯一标识 user_{uuid}")
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="登录用户名")
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="显示名称")
    email: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, comment="邮箱")
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False, comment="哈希密码")
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="OPERATOR", comment="角色: ADMIN/OPERATOR/VIEWER")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, comment="是否启用")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        default=func.now(), onupdate=func.now(),
        comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )

    # 关联
    sessions: Mapped[list["MaoSession"]] = relationship(back_populates="user")  # type: ignore[name-defined]
    agents: Mapped[list["MaoAgent"]] = relationship(back_populates="creator")  # type: ignore[name-defined]
