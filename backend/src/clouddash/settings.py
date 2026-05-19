from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives at repo root: assignment/
# parents[0]=clouddash, [1]=src, [2]=backend, [3]=assignment
_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM provider — google is the default now (nvidia was too slow for demos)
    llm_provider: Literal["google", "groq", "nvidia", "sarvam"] = Field(default="google")
    google_api_key: str = Field(default="")
    groq_api_key: str = Field(default="")
    nvidia_api_key: str = Field(default="")
    sarvam_api_key: str = Field(default="")

    # model split: reasoning for specialists, fast for triage/rewrite/guardrails
    llm_reasoning_model: str = Field(default="gemini-2.5-pro")
    llm_fast_model: str = Field(default="gemini-2.5-flash")
    llm_judge_model: str = Field(default="gemini-2.5-pro")
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_retries: int = Field(default=3)
    llm_timeout_seconds: int = Field(default=60)

    # Sarvam — separate endpoint + models. verified May 14: auth is Bearer NOT api-subscription-key
    # despite what their docs say. both work actually. using Bearer for simplicity.
    sarvam_base_url: str = Field(default="https://api.sarvam.ai/v1")
    sarvam_reasoning_model: str = Field(default="sarvam-105b")
    sarvam_fast_model: str = Field(default="sarvam-30b")

    # LangSmith — on by default if key is set
    langchain_tracing_v2: bool = Field(default=False)
    langchain_api_key: str = Field(default="")
    langchain_project: str = Field(default="clouddash-multi-agent")
    langchain_endpoint: str = Field(default="https://api.smith.langchain.com")

    # retrieval
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5")
    chroma_persist_dir: str = Field(default=str(_BACKEND_ROOT / "data" / "chroma"))
    chroma_collection_name: str = Field(default="clouddash_kb")
    retrieval_top_k_dense: int = Field(default=10)
    retrieval_top_k_bm25: int = Field(default=10)
    retrieval_top_k_fused: int = Field(default=10)
    retrieval_top_k_reranked: int = Field(default=5)
    # TODO(mohan): swap to Qdrant when we hit 100k docs. Chroma's HNSW gets weird past that.
    reranker_type: Literal["cohere", "llm", "none"] = Field(default="cohere")
    cohere_api_key: str = Field(default="")
    grounding_min_score: float = Field(default=0.3)
    tavily_api_key: str = Field(default="")

    # app
    app_env: Literal["development", "production", "test"] = Field(default="development")
    log_level: str = Field(default="INFO")
    log_dir: str = Field(default=str(_BACKEND_ROOT / "logs"))
    audit_log_path: str = Field(default=str(_BACKEND_ROOT / "logs" / "audit.jsonl"))
    graph_checkpoint_path: str = Field(default=str(_BACKEND_ROOT / "data" / "graph_checkpoints.sqlite"))
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # guardrails
    max_input_length: int = Field(default=4000)
    max_turns_per_conversation: int = Field(default=20)
    self_correction_max_attempts: int = Field(default=2)

    # paths
    agents_config_path: str = Field(default=str(_BACKEND_ROOT / "config" / "agents.yaml"))
    routing_config_path: str = Field(default=str(_BACKEND_ROOT / "config" / "routing.yaml"))
    prompts_dir: str = Field(
        default=str(Path(__file__).parent / "prompts")
    )
    kb_root_dir: str = Field(default=str(_BACKEND_ROOT / "knowledge_base"))
    mock_crm_path: str = Field(default=str(_BACKEND_ROOT / "data" / "mock_customers.json"))

    eval_scenario_sleep_s: float = Field(default=2.0)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def ensure_dirs(self) -> None:
        for p in (self.log_dir, self.chroma_persist_dir, str(Path(self.graph_checkpoint_path).parent)):
            Path(p).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
