"""Application configuration — single source of truth, loaded from environment.

We use pydantic-settings for type-safe env loading with sensible defaults.
Every component imports `get_settings()` rather than reading os.environ directly,
so configuration is testable and overridable.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All runtime configuration for CloudDash."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- LLM provider ----
    llm_provider: Literal["google", "groq", "nvidia"] = Field(
        default="google",
        description="Which LLM provider to use. All three supported via LangChain.",
    )
    google_api_key: str = Field(
        default="",
        description="Google AI Studio API key for Gemini (when llm_provider=google).",
    )
    groq_api_key: str = Field(
        default="",
        description="Groq API key (when llm_provider=groq).",
    )
    nvidia_api_key: str = Field(
        default="",
        description="NVIDIA AI Endpoints (build.nvidia.com) key (when llm_provider=nvidia).",
    )
    llm_reasoning_model: str = Field(
        default="gemini-2.5-pro",
        description="Strong reasoning model used by specialist agents.",
    )
    llm_fast_model: str = Field(
        default="gemini-2.5-flash",
        description="Fast/cheap model for triage, guardrails, judge, reranker.",
    )
    llm_judge_model: str = Field(
        default="gemini-2.5-pro",
        description="Stricter model used by the eval LLM-as-judge.",
    )
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_retries: int = Field(default=3, ge=0, le=10)
    llm_timeout_seconds: int = Field(default=60, ge=5, le=300)

    # ---- Observability ----
    langchain_tracing_v2: bool = Field(default=False)
    langchain_api_key: str = Field(default="")
    langchain_project: str = Field(default="clouddash-multi-agent")
    langchain_endpoint: str = Field(default="https://api.smith.langchain.com")

    # ---- Retrieval ----
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5")
    chroma_persist_dir: str = Field(default=str(PROJECT_ROOT / "data" / "chroma"))
    chroma_collection_name: str = Field(default="clouddash_kb")
    retrieval_top_k_dense: int = Field(default=10, ge=1, le=50)
    retrieval_top_k_bm25: int = Field(default=10, ge=1, le=50)
    retrieval_top_k_fused: int = Field(default=10, ge=1, le=50)
    retrieval_top_k_reranked: int = Field(default=3, ge=1, le=20)
    reranker_type: Literal["llm", "cross_encoder", "none"] = Field(default="llm")
    grounding_min_score: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Below this composite score, agent must trigger 'not in KB' path.",
    )

    # ---- KB paths ----
    kb_root_dir: str = Field(default=str(PROJECT_ROOT / "knowledge_base"))

    # ---- Application ----
    app_env: Literal["development", "production", "test"] = Field(default="development")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    log_dir: str = Field(default=str(PROJECT_ROOT / "logs"))
    audit_log_path: str = Field(default=str(PROJECT_ROOT / "logs" / "audit.jsonl"))
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)

    # ---- Guardrails ----
    max_input_length: int = Field(default=4000, ge=1)
    max_turns_per_conversation: int = Field(default=20, ge=1)
    self_correction_max_attempts: int = Field(default=2, ge=0, le=5)

    # ---- Agent registry ----
    agents_config_path: str = Field(default=str(PROJECT_ROOT / "config" / "agents.yaml"))
    routing_config_path: str = Field(default=str(PROJECT_ROOT / "config" / "routing.yaml"))
    prompts_dir: str = Field(default=str(PROJECT_ROOT / "src" / "clouddash" / "prompts"))

    # ---- Mock CRM ----
    mock_crm_path: str = Field(default=str(PROJECT_ROOT / "data" / "mock_customers.json"))

    # ---- Convenience properties ----
    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def ensure_directories(self) -> None:
        """Create runtime directories if missing. Called on startup."""
        for path_str in (self.log_dir, self.chroma_persist_dir):
            Path(path_str).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton accessor — cached so we read env once."""
    return Settings()


def reload_settings() -> Settings:
    """For tests: clear the cache and reload."""
    get_settings.cache_clear()
    return get_settings()
