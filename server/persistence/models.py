from __future__ import annotations

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from server.config.constants import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_LLM_MAX_TOKENS,
    DEFAULT_LLM_TEMPERATURE,
)


class Base(DeclarativeBase):
    pass


class BoolInt(TypeDecorator[int]):
    impl = Integer
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return int(bool(value)) if value is not None else None

    def process_result_value(self, value, dialect):
        return bool(value) if value is not None else None


class SessionRecord(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default="New Session")
    mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="build")
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="created")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_root: Mapped[str] = mapped_column(Text, nullable=False, server_default=".")
    is_active: Mapped[bool] = mapped_column(BoolInt, nullable=False, server_default="1")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    parent_session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_output: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    plan_approved_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_cost: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_state: Mapped[str] = mapped_column(Text, nullable=False, server_default="idle")
    context_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    context_window: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    context_percent: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    export_format: Mapped[str | None] = mapped_column(Text, nullable=True)
    exported_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(BoolInt, nullable=False, server_default="0")


Index("idx_sessions_active", SessionRecord.is_active)
Index("idx_sessions_state", SessionRecord.state)
Index("idx_sessions_updated", SessionRecord.updated_at)
Index("idx_sessions_parent", SessionRecord.parent_session_id)


class MessageRecord(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    events_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")


Index("idx_messages_session", MessageRecord.session_id)
Index("idx_messages_created", MessageRecord.created_at)


class ProviderRecord(Base):
    __tablename__ = "providers"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    api_key: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    model: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    base_url: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    max_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=str(DEFAULT_LLM_MAX_TOKENS)
    )
    temperature: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=str(DEFAULT_LLM_TEMPERATURE)
    )
    is_active: Mapped[bool] = mapped_column(BoolInt, nullable=False, server_default="0")
    swatch_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    adapter_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="openai_compat")
    capabilities_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    api_key_prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(BoolInt, nullable=False, server_default="0")


Index("idx_providers_active", ProviderRecord.is_active)


class ProviderModelRecord(Base):
    __tablename__ = "provider_models"
    __table_args__ = (PrimaryKeyConstraint("provider_id", "id"),)
    id: Mapped[str] = mapped_column(Text, nullable=False)
    provider_id: Mapped[str] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    context_window: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=str(DEFAULT_CONTEXT_WINDOW)
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    is_default: Mapped[bool] = mapped_column(BoolInt, nullable=False, server_default="0")


Index("idx_provider_models_pid", ProviderModelRecord.provider_id)


class AppSettingRecord(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class CatalogProviderRecord(Base):
    __tablename__ = "catalog_providers"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    adapter: Mapped[str] = mapped_column(Text, nullable=False, server_default="openai_compat")
    litellm_prefix: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    default_model: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    base_url: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    api_key_prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_api_key: Mapped[bool] = mapped_column(BoolInt, nullable=False, server_default="1")
    swatch_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    capabilities_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    config_fields_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    options_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    env_keys_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    is_popular: Mapped[bool] = mapped_column(BoolInt, nullable=False, server_default="0")
    base_url_style: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    supports_prompt_caching: Mapped[bool] = mapped_column(
        BoolInt, nullable=False, server_default="0"
    )
    supports_thinking_headers: Mapped[bool] = mapped_column(
        BoolInt, nullable=False, server_default="0"
    )
    custom_flow: Mapped[bool] = mapped_column(BoolInt, nullable=False, server_default="0")
    rate_limit_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class CatalogModelRecord(Base):
    __tablename__ = "catalog_models"
    __table_args__ = (PrimaryKeyConstraint("provider_id", "id"),)
    provider_id: Mapped[str] = mapped_column(
        ForeignKey("catalog_providers.id", ondelete="CASCADE"), nullable=False
    )
    id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    context_window: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=str(DEFAULT_CONTEXT_WINDOW)
    )
    parameters: Mapped[str | None] = mapped_column(Text, nullable=True)
    architecture: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_modalities: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    output_modalities: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    tags: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    model_capabilities_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    speed_tier: Mapped[str | None] = mapped_column(Text, nullable=True)
    best_for: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    pricing_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    is_default: Mapped[bool] = mapped_column(BoolInt, nullable=False, server_default="0")
    tokenizer: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    prompt_tier: Mapped[str] = mapped_column(Text, nullable=False, server_default="")


Index("idx_catalog_models_provider", CatalogModelRecord.provider_id)


class TokenUsageRecord(Base):
    __tablename__ = "token_usage"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    model: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # QA-10: composed-context occupancy at record time — distinct from the
    # provider-billed total_tokens above. 0 means "unknown" (pre-QA-10 rows).
    context_occupancy: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    context_window: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    percent: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cache_write_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    step_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="-1")
    estimated: Mapped[bool] = mapped_column(BoolInt, nullable=False, server_default="0")
    is_retry: Mapped[bool] = mapped_column(BoolInt, nullable=False, server_default="0")
    retry_of: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


Index("idx_token_usage_session", TokenUsageRecord.session_id)
Index("idx_token_usage_step", TokenUsageRecord.session_id, TokenUsageRecord.step_index)
Index("idx_token_usage_model", TokenUsageRecord.provider, TokenUsageRecord.model)


class ContextDegradationRecord(Base):
    __tablename__ = "context_degradation"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    before_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    after_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class PricingRecord(Base):
    __tablename__ = "pricing"
    __table_args__ = (PrimaryKeyConstraint("provider", "model_id"),)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    input_1m: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    output_1m: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    cache_read_1m: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    cache_creation_1m: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class BudgetSettingsRecord(Base):
    __tablename__ = "budget_settings"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    max_session_cost: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    max_daily_cost: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    max_monthly_cost: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    active: Mapped[bool] = mapped_column(BoolInt, nullable=False, server_default="1")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(BoolInt, nullable=False, server_default="0")


class SessionCheckpointRecord(Base):
    __tablename__ = "session_checkpoints"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    checkpoint_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="automatic")
    step_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    snapshot_data: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


Index("idx_checkpoints_session", SessionCheckpointRecord.session_id)


class SyncEventRecord(Base):
    __tablename__ = "sync_events"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_data: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


Index("idx_sync_events_session_seq", SyncEventRecord.session_id, SyncEventRecord.sequence)


class SessionStatusHistoryRecord(Base):
    __tablename__ = "session_status_history"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    from_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_state: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


Index("idx_status_history_session", SessionStatusHistoryRecord.session_id)


class SessionDraftRecord(Base):
    __tablename__ = "session_drafts"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    context: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


Index("idx_drafts_session", SessionDraftRecord.session_id)
Index("idx_drafts_expires", SessionDraftRecord.expires_at)


class PermissionRecord(Base):
    __tablename__ = "permissions"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(BoolInt, nullable=False, server_default="0")


Index("idx_permissions_tool", PermissionRecord.tool_name)
Index("idx_permissions_session", PermissionRecord.session_id)


class SessionWorkspaceRecord(Base):
    __tablename__ = "session_workspace"
    __table_args__ = (
        UniqueConstraint("session_id", "path", name="uq_session_workspace_session_path"),
    )
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    size: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    writes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    edits: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_read_at: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    last_edited_at: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


Index("idx_session_workspace_session", SessionWorkspaceRecord.session_id)
Index(
    "idx_session_workspace_session_path",
    SessionWorkspaceRecord.session_id,
    SessionWorkspaceRecord.path,
    unique=True,
)


class ProjectMemoryRecord(Base):
    """DB-backed project-level memory (cross-session learnings)."""

    __tablename__ = "project_memory"
    __table_args__ = (UniqueConstraint("workspace_root", "key", name="uq_project_memory_ws_key"),)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    workspace_root: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


Index(
    "idx_project_memory_ws",
    ProjectMemoryRecord.workspace_root,
)
