"""
VectorSearchTool - Semantic search across documents.

Performs vector similarity search using ChromaDB embeddings to find relevant
invoices, contracts, and budgets based on natural language queries.
"""

import structlog
from typing import Dict, Any, Optional, List

from backend.vector.client import ChromaDBClient

logger = structlog.get_logger()


class VectorSearchTool:
    """
    Tool for semantic search across documents using vector embeddings.

    Capabilities:
    - Search invoices by description/content
    - Find similar contracts or budgets
    - Semantic matching for natural language queries
    - Returns ranked results by similarity score
    """

    def __init__(self):
        """Initialize with ChromaDB client."""
        self.chroma_client = ChromaDBClient()

    def run(
        self,
        query: str = "",
        action: str = "",
        collection: str = "invoices",
        n_results: int = 5,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Perform semantic search across documents.

        Args:
            query: User's original query
            action: Specific search action (e.g., "Search for electrical work invoices")
            collection: Collection to search ("invoices", "contracts", "budgets")
            n_results: Number of results to return (default 5)
            **kwargs: Additional context (e.g., previous_results)

        Returns:
            {
                "query": "<search query>",
                "results": [...],  # Matching documents with metadata
                "count": 3,
                "collection": "invoices",
                "status": "success" | "failed"
            }
        """
        # Extract search query from action or use query
        search_query = action if action else query

        logger.info(
            "vector_search_executing",
            query=search_query[:100],
            collection=collection,
            n_results=n_results,
        )

        try:
            # Perform vector search
            results = self.chroma_client.search(
                collection_name=collection,
                query_text=search_query,
                n_results=n_results,
            )

            # Format results
            formatted_results = []
            if results and "documents" in results:
                documents = results["documents"][0] if results["documents"] else []
                metadatas = results["metadatas"][0] if results.get("metadatas") else []
                distances = results["distances"][0] if results.get("distances") else []

                for idx, doc in enumerate(documents):
                    formatted_results.append({
                        "document": doc,
                        "metadata": metadatas[idx] if idx < len(metadatas) else {},
                        "similarity": 1 - distances[idx] if idx < len(distances) else 0,
                        "rank": idx + 1,
                    })

            logger.info("vector_search_complete", result_count=len(formatted_results))

            return {
                "query": search_query,
                "results": formatted_results,
                "count": len(formatted_results),
                "collection": collection,
                "status": "success",
            }

        except Exception as e:
            logger.error("vector_search_failed", error=str(e), query=search_query[:100])
            return {
                "error": str(e),
                "query": search_query,
                "collection": collection,
                "status": "failed",
            }

    def search_invoices(self, query: str, n_results: int = 5) -> Dict[str, Any]:
        """
        Search invoices by semantic similarity.

        Args:
            query: Natural language search query
            n_results: Number of results to return

        Returns:
            Search results with invoice metadata
        """
        return self.run(query=query, collection="invoices", n_results=n_results)

    def search_contracts(self, query: str, n_results: int = 5) -> Dict[str, Any]:
        """
        Search contracts by semantic similarity.

        Args:
            query: Natural language search query
            n_results: Number of results to return

        Returns:
            Search results with contract metadata
        """
        return self.run(query=query, collection="contracts", n_results=n_results)

    def search_budgets(self, query: str, n_results: int = 5) -> Dict[str, Any]:
        """
        Search budgets by semantic similarity.

        Args:
            query: Natural language search query
            n_results: Number of results to return

        Returns:
            Search results with budget metadata
        """
        return self.run(query=query, collection="budgets", n_results=n_results)
