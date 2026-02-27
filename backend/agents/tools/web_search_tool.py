"""
WebSearchTool - Web search for external information.

High-priority tool for market rates, contractor verification, and industry standards.
Uses Tavily Search API for reliable, AI-optimized search results.
"""

from backend.core.logging import get_logger
from typing import Dict, Any, Optional

logger = get_logger(__name__)


class WebSearchTool:
    """
    Tool for searching the web.

    Use cases:
    - Market rates: "What's the average cost of concrete work in Seattle 2026?"
    - Contractor background: "ABC Contractors reviews Seattle"
    - Industry standards: "Standard retention rate for construction contracts"
    - Regulations: "Washington state contractor license requirements"
    """

    def __init__(self):
        """Initialize with Tavily client if API key available."""
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize Tavily client."""
        try:
            from backend.core.config import settings

            # Check if Tavily API key is configured
            tavily_key = getattr(settings, 'tavily_api_key', None)

            if tavily_key:
                from tavily import TavilyClient
                self.client = TavilyClient(api_key=tavily_key)
                logger.info("web_search_tool_initialized", provider="tavily")
            else:
                logger.warning("web_search_tool_no_api_key",
                             message="Tavily API key not configured, web search disabled")
        except ImportError:
            logger.warning("web_search_tool_import_failed",
                         message="Tavily package not installed")
        except Exception as e:
            logger.error("web_search_tool_init_failed", error=str(e))

    def run(
        self,
        query: str = "",
        action: str = "",
        context: Optional[Dict[str, Any]] = None,
        num_results: int = 5,
    ) -> Dict[str, Any]:
        """
        Search the web for information.

        Args:
            query: User's original query
            action: Specific search query or action
            context: Additional context (not used for web search)
            num_results: Number of results to return (default: 5)

        Returns:
            {
                "query": "<search query>",
                "results": [
                    {"title": "...", "url": "...", "snippet": "..."},
                    ...
                ],
                "answer": "<AI-generated summary>",  # If available
                "sources_count": 5
            }
        """
        # Use action as search query if provided, otherwise use query
        search_query = action if action else query

        logger.info("web_search_executing", query=search_query[:100])

        # Check if client is available
        if not self.client:
            logger.warning("web_search_unavailable")
            return {
                "error": "Web search is not configured. Please add TAVILY_API_KEY to .env file.",
                "query": search_query,
                "status": "unavailable",
            }

        try:
            # Execute search
            results = self.client.search(
                query=search_query,
                max_results=num_results,
                search_depth="basic",  # or "advanced" for deeper search
            )

            # Format results
            formatted_results = []
            for r in results.get("results", []):
                formatted_results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", "")[:300],  # Limit to 300 chars
                })

            response = {
                "query": search_query,
                "results": formatted_results,
                "sources_count": len(formatted_results),
            }

            # Add AI-generated answer if available
            if "answer" in results:
                response["answer"] = results["answer"]

            logger.info(
                "web_search_complete",
                query=search_query[:50],
                results_count=len(formatted_results),
            )

            return response

        except Exception as e:
            logger.error("web_search_failed", error=str(e), query=search_query[:100])
            return {
                "error": f"Web search failed: {str(e)}",
                "query": search_query,
                "status": "failed",
            }
