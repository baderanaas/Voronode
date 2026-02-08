from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False
    )

    # LLM
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"
    groq_extraction_temperature: float = 0.1
    groq_validation_temperature: float = 0.3
    groq_max_retries: int = 3

    # Embeddings
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "voronode123"

    # ChromaDB
    chromadb_host: str = "localhost"
    chromadb_port: int = 8000

    # Invoice Processing
    invoice_extraction_timeout: int = 30
    enable_semantic_validation: bool = True

    # API
    api_upload_max_size: int = 10 * 1024 * 1024  # 10MB

    # Workflow configuration (Phase 3)
    workflow_max_retries: int = 3
    workflow_checkpoint_db: str = "workflow_checkpoints.db"
    workflow_state_db: str = "workflow_states.db"
    workflow_quarantine_high_risk: bool = True

    # General
    log_level: str = "INFO"


settings = Settings()
