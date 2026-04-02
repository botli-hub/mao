"""渠道适配相关 ORM 模型 — mao_channel_account / mao_channel_session / mao_offline_inbox"""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mao.db.database import Base


class MaoChannelAccount(Base):
    """渠道账号绑定表 — 飞书 OpenID → 系统 UserID 映射。"""
    __tablename__ = "mao_channel_account"
    __table_args__ = (
        Index("ix_mao_channel_account_updated_at", "updated_at"),
        Index("ix_mao_channel_account_created_at", "created_at"),
        Index("ix_mao_channel_account_user_id", "user_id"),
        {"comment": "渠道账号绑定表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="系统 user_id")
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="渠道类型: FEISHU/DINGTALK/WECOM")
    external_user_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="渠道侧用户 ID（如飞书 OpenID）")
    external_app_id: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="外部应用 ID（如飞书 App ID）")
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True, comment="渠道 OAuth2 访问令牌（加密存储）")
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="令牌过期时间")
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="渠道额外信息（如飞书 UnionID）")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )


class MaoChannelSession(Base):
    """渠道会话映射表 — 飞书 ChatID → MAO SessionID 映射。"""
    __tablename__ = "mao_channel_session"
    __table_args__ = (
        Index("ix_mao_channel_session_updated_at", "updated_at"),
        Index("ix_mao_channel_session_created_at", "created_at"),
        Index("ix_mao_channel_session_session_id", "session_id"),
        {"comment": "渠道会话映射表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="MAO 会话 ID")
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="渠道类型")
    external_chat_id: Mapped[str] = mapped_column(String(256), nullable=False, comment="渠道侧会话 ID（如飞书 ChatID，最长约 100 字符）")
    external_app_id: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="外部应用 ID")
    external_msg_id: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="最近一条渠道消息 ID（用于回复线程）")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )


class MaoOfflineInbox(Base):
    """离线信箱表 — 用户离线时暂存消息，支持指数退避重投。"""
    __tablename__ = "mao_offline_inbox"
    __table_args__ = (
        Index("ix_mao_offline_inbox_updated_at", "updated_at"),
        Index("ix_mao_offline_inbox_created_at", "created_at"),
        Index("ix_mao_offline_inbox_user_id", "user_id"),
        Index("ix_mao_offline_inbox_retry_count", "retry_count"),
        Index("ix_mao_offline_inbox_last_retry_at", "last_retry_at"),
        {"comment": "离线信箱表（支持指数退避重投）"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="目标用户 user_id")
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属会话 ID")
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="关联任务 ID")
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False, default="WEB", comment="目标渠道类型")
    message_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="消息类型: TASK_SUMMARY/CARD/SYSTEM_NOTICE")
    message_content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="消息文本内容")
    card_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="卡片 Schema（消息类型为 CARD 时）")
    is_read: Mapped[bool] = mapped_column(nullable=False, default=False, comment="是否已读")
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="阅读时间")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="重投次数（指数退避：1min→5min→15min）")
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近一次重投时间")
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=5, comment="最大重投次数（超出后转死信队列）")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )
