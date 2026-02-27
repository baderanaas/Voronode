import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions
from typing import Optional
from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class ChromaDBClient:
    def __init__(self):
        self.client = chromadb.HttpClient(
            host=settings.chromadb_host,
            port=settings.chromadb_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        # Initialize OpenAI embedding function
        self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
            api_key=settings.openai_api_key,
            model_name=settings.openai_embedding_model,
        )
        self._init_collections()

    def _get_or_recreate_collection(self, name: str, description: str):
        """
        Get or create a collection, automatically recreating it if the stored
        embedding model doesn't match the current one (prevents dimension mismatch).
        """
        meta = {
            "description": description,
            "embedding_model": settings.openai_embedding_model,
        }
        try:
            col = self.client.get_collection(name)
            stored_model = col.metadata.get("embedding_model", "")
            if stored_model != settings.openai_embedding_model:
                logger.warning(
                    "chromadb_model_mismatch_recreating",
                    collection=name,
                    stored=stored_model,
                    current=settings.openai_embedding_model,
                )
                self.client.delete_collection(name)
                col = self.client.create_collection(
                    name=name, metadata=meta, embedding_function=self.embedding_function
                )
            else:
                # Reattach embedding function (get_collection doesn't store it)
                col = self.client.get_or_create_collection(
                    name=name, metadata=meta, embedding_function=self.embedding_function
                )
        except Exception:
            col = self.client.get_or_create_collection(
                name=name, metadata=meta, embedding_function=self.embedding_function
            )
        return col

    def _init_collections(self):
        """Create collections for different document types."""
        self.contracts_collection = self._get_or_recreate_collection(
            "contracts", "Contract text and clauses"
        )
        self.emails_collection = self._get_or_recreate_collection(
            "emails", "Email threads and communications"
        )
        self.invoices_collection = self._get_or_recreate_collection(
            "invoices", "Invoice text for semantic search"
        )

    def verify_connectivity(self) -> bool:
        """Test connection to ChromaDB"""
        try:
            self.client.heartbeat()
            return True
        except Exception as e:
            logger.error("chromadb_connection_failed", error=str(e))
            return False

    def search(
        self,
        collection_name: str,
        query_text: str,
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> dict:
        """Semantic similarity search across a collection."""
        collection_map = {
            "invoices": self.invoices_collection,
            "contracts": self.contracts_collection,
            "emails": self.emails_collection,
        }
        collection = collection_map.get(collection_name)
        if collection is None:
            collection = self.client.get_or_create_collection(
                name=collection_name,
                embedding_function=self.embedding_function,
            )
        kwargs: dict = {"query_texts": [query_text], "n_results": n_results}
        if where:
            kwargs["where"] = where
        return collection.query(**kwargs)

    def add_document(
        self, collection_name: str, doc_id: str, text: str, metadata: dict
    ):
        """Add document to vector store"""
        collection = self.client.get_collection(collection_name)
        collection.add(ids=[doc_id], documents=[text], metadatas=[metadata])
