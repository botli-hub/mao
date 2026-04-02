"""技能表 ORM 模型 — mao_skill"""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mao.db.database import Base


class MaoSkill(Base):
    __tablename__ = "mao_skill"
    __table_args__ = (
        Index("ix_mao_skill_updated_at", "updated_at"),
        Index("ix_mao_skill_created_at", "created_at"),
        Index("ix_mao_skill_type", "skill_type"),
        {"comment": "技能注册表"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    skill_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="技能唯一标识 skill_{uuid}")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="技能名称（英文，供 LLM 识别）")
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="技能显示名称（中文）")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="技能功能描述（供 Router 和 LLM 理解）")
    skill_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="技能类型: API/VIEW/ASYNC/MACRO")
    endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="API 端点 URL")
    http_method: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="HTTP 方法: GET/POST/PUT/DELETE")
    input_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="输入参数 JSON Schema（Pydantic 生成）")
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="输出结果 JSON Schema")
    auth_type: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="鉴权类型: NONE/API_KEY/OAUTH2/BEARER")
    auth_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="鉴权配置（加密存储）")
    mao_control_meta: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True,
        comment="MAO 控制元数据: {x_mao_suspend, ttl_seconds, callback_expect}"
    )
    card_schema_template: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="VIEW 类型技能的卡片模板")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, comment="是否启用")
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0", comment="技能版本号")
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="创建者 user_id")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), comment="创建时间"
    )
