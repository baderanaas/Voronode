import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions
from backend.core.config import settings
import structlog

logger = structlog.get_logger()


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

    def _init_collections(self):
        """Create collections for different document types"""
        self.contracts_collection = self.client.get_or_create_collection(
            name="contracts",
            metadata={"description": "Contract text and clauses"},
            embedding_function=self.embedding_function,
        )
        self.emails_collection = self.client.get_or_create_collection(
            name="emails",
            metadata={"description": "Email threads and communications"},
            embedding_function=self.embedding_function,
        )
        self.invoices_collection = self.client.get_or_create_collection(
            name="invoices",
            metadata={"description": "Invoice text for semantic search"},
            embedding_function=self.embedding_function,
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
        return collection.query(query_texts=[query_text], n_results=n_results)

    def add_document(
        self, collection_name: str, doc_id: str, text: str, metadata: dict
    ):
        """Add document to vector store"""
        collection = self.client.get_collection(collection_name)
        collection.add(ids=[doc_id], documents=[text], metadatas=[metadata])
