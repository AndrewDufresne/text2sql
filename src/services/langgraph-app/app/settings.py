"""Runtime configuration (env-driven). All defaults safe for local dev."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # App
    app_version: str = Field("1.0.0-rc1", alias="APP_VERSION")
    log_level: str = Field("INFO", alias="LANGGRAPH_LOG_LEVEL")

    # LiteLLM (OpenAI-compatible)
    litellm_base_url: str = Field("http://litellm:4000", alias="LITELLM_BASE_URL")
    litellm_api_key: str = Field("sk-litellm-dev-only", alias="LITELLM_API_KEY")
    litellm_model: str = Field("router/sql-gen", alias="LITELLM_MODEL")
    llm_timeout_s: float = Field(60.0, alias="LLM_TIMEOUT_S")

    # Trino
    trino_host: str = Field("trino", alias="TRINO_HOST")
    trino_port: int = Field(8080, alias="TRINO_PORT")
    trino_catalog: str = Field("cib", alias="TRINO_CATALOG")
    trino_schema: str = Field("public", alias="TRINO_SCHEMA")
    trino_source: str = Field("text2sql-langgraph", alias="TRINO_SOURCE")

    # Langfuse
    langfuse_host: str = Field("http://langfuse:3000", alias="LANGFUSE_HOST")
    langfuse_public_key: str = Field("", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field("", alias="LANGFUSE_SECRET_KEY")

    # ---- Phase 2 ----
    # Presidio
    presidio_analyzer_url: str = Field("http://presidio-analyzer:3000", alias="PRESIDIO_ANALYZER_URL")
    presidio_anonymizer_url: str = Field("http://presidio-anonymizer:3000", alias="PRESIDIO_ANONYMIZER_URL")
    pii_enabled: bool = Field(True, alias="PII_ENABLED")
    pii_score_threshold: float = Field(0.5, alias="PII_SCORE_THRESHOLD")

    # OPA
    opa_url: str = Field("http://opa:8181", alias="OPA_URL")
    opa_enabled: bool = Field(True, alias="OPA_ENABLED")
    opa_decision_path: str = Field("text2sql/decision", alias="OPA_DECISION_PATH")

    # TEI + pgvector schema-link
    tei_url: str = Field("http://tei-embed:80", alias="TEI_URL")
    pgv_dsn: str = Field(
        "postgresql://cib:cib_dev_only@postgres-cib:5432/cib", alias="PGV_DSN"
    )
    chat_store_dsn: str = Field(
        "postgresql://t2sql:t2sql_dev_only@postgres-platform:5432/t2sql_platform",
        alias="CHAT_STORE_DSN",
    )
    schema_link_enabled: bool = Field(True, alias="SCHEMA_LINK_ENABLED")
    schema_link_top_k: int = Field(3, alias="SCHEMA_LINK_TOP_K")
    embedding_dim: int = Field(384, alias="EMBEDDING_DIM")

    # Phase 1 limits / Phase 2 self-repair
    row_limit_default: int = 1000
    row_limit_hard_max: int = 10_000
    self_repair_max: int = Field(1, alias="SELF_REPAIR_MAX")

    # ---- Phase 3 (HITL + Eval) ----
    # Output PII masking (post-execute)
    output_mask_enabled: bool = Field(True, alias="OUTPUT_MASK_ENABLED")

    # NL explanation
    explain_enabled: bool = Field(True, alias="EXPLAIN_ENABLED")
    litellm_explain_model: str = Field(
        "router/sql-gen", alias="LITELLM_EXPLAIN_MODEL"
    )
    explain_max_tokens: int = Field(180, alias="EXPLAIN_MAX_TOKENS")

    # Argilla HITL feedback sink
    argilla_enabled: bool = Field(False, alias="ARGILLA_ENABLED")
    argilla_url: str = Field("http://argilla:6900", alias="ARGILLA_URL")
    argilla_api_key: str = Field("argilla.apikey", alias="ARGILLA_API_KEY")
    argilla_workspace: str = Field("admin", alias="ARGILLA_WORKSPACE")
    argilla_dataset: str = Field("text2sql-feedback", alias="ARGILLA_DATASET")
    feedback_local_path: str = Field(
        "/tmp/text2sql-feedback.jsonl", alias="FEEDBACK_LOCAL_PATH"
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
