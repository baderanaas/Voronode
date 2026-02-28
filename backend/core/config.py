from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # LLM
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"
    groq_extraction_temperature: float = 0.1
    groq_validation_temperature: float = 0.3
    groq_max_retries: int = 3

    # Embeddings
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"

    # Multi-Agent Chat
    openai_chat_model: str = "gpt-4o-mini"  # For conversational agents

    # Gemini (for Planner agent)
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-pro"  # For planner agent

    # Anthropic (for Cypher query tool)
    anthropic_api_key: str
    anthropic_model: str = "claude-haiku-4-5-20251001"  # For Cypher query generation

    # Web Search
    tavily_api_key: Optional[str] = None  # Optional for WebSearchTool

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

    # Workflow configuration
    workflow_max_retries: int = 3
    workflow_quarantine_high_risk: bool = True

    # Compliance Auditor
    enable_compliance_audit: bool = True
    compliance_price_tolerance_percent: float = 0.05
    compliance_retention_tolerance_percent: float = 0.01
    compliance_quarantine_on_violation: bool = True
    compliance_critical_threshold: int = 1
    compliance_high_threshold: int = 2

    # Database (Postgres — replaces all SQLite databases)
    database_url: str = "postgresql://postgres:postgres@localhost:5432/voronode"

    # Memory / conversation persistence
    conversation_window_size: int = 10   # recent messages sent to planner
    memory_search_limit: int = 5         # Mem0 memories injected per request
    memory_max_chars: int = 1500         # cap on total memory text

    # JWT Authentication
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60 * 24  # 24 hours

    # General
    log_level: str = "INFO"


settings = Settings()
