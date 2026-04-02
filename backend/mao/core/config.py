"""
MAO 平台核心配置管理
使用 pydantic-settings 从环境变量/`.env` 文件加载配置，支持类型校验。
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 应用基础 ──────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_secret_key: str = Field(min_length=32)
    app_debug: bool = False
    app_log_level: str = "INFO"

    # ── 数据库 ────────────────────────────────────────────────
    database_url: str
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_state_db: int = 1
    redis_task_snapshot_ttl: int = 86400  # 24h

    # ── Kafka ─────────────────────────────────────────────────
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "mao-backend"
    kafka_topic_audit_thought: str = "mao.audit.thought"
    kafka_topic_audit_action: str = "mao.audit.action"
    kafka_topic_audit_card_emit: str = "mao.audit.card_emit"
    kafka_topic_audit_callback: str = "mao.audit.callback"

    # ── 大模型 ────────────────────────────────────────────────
    openai_api_key: str
    openai_base_url: str = "https://api.openai.com/v1"
    openai_default_model: str = "gpt-4o"
    openai_router_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # ── 飞书 ──────────────────────────────────────────────────
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_verification_token: str = ""
    feishu_encrypt_key: str = ""

    # ── JWT ───────────────────────────────────────────────────
    jwt_secret_key: str = Field(min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 480

    # ── 执行引擎 ──────────────────────────────────────────────
    engine_max_steps: int = 7
    engine_step_timeout_seconds: int = 30
    engine_max_retries: int = 3
    engine_circuit_breaker_threshold: int = 3
    engine_llm_retry_attempts: int = 3
    engine_llm_retry_base_delay_seconds: float = 0.5
    engine_semantic_cache_enabled: bool = True
    engine_semantic_cache_threshold: float = 0.92
    engine_semantic_cache_top_k: int = 20
    engine_semantic_cache_ttl_seconds: int = 3600
    engine_semantic_cache_max_items: int = 200
    engine_hitl_default_ttl_seconds: int = 3600


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例（线程安全，进程内缓存）。"""
    return Settings()  # type: ignore[call-arg]
