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

    # General
    log_level: str = "INFO"


settings = Settings()
