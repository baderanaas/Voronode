"""Singleton Mem0 client — extracts and retrieves facts across conversations."""

import asyncio

from mem0 import Memory
from backend.core.logging import get_logger

from backend.core.config import settings

logger = get_logger(__name__)

_FAILED = object()  # sentinel: init was attempted but failed
_instance = None


class Mem0Client:
    """Thin wrapper around mem0.Memory with safe error handling."""

    def __init__(self):
        global _instance
        if _instance is None:
            config = {
                "llm": {
                    "provider": "openai",
                    "config": {
                        "model": settings.openai_chat_model,
                        "temperature": 0.1,
                        "api_key": settings.openai_api_key,
                    },
                },
                "embedder": {
                    "provider": "openai",
                    "config": {
                        "model": settings.openai_embedding_model,
                        "api_key": settings.openai_api_key,
                    },
                },
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "host": settings.chromadb_host,
                        "port": settings.chromadb_port,
                        "collection_name": "memories",
                    },
                },
            }
            try:
                _instance = Memory.from_config(config)
            except Exception as exc:
                logger.error("mem0_init_failed", error=str(exc))
                _instance = _FAILED

        self._memory = _instance if _instance is not _FAILED else None

    async def add_turn(self, messages: list[dict], user_id: str = "default_user"):
        """Extract and store facts from a conversation turn (non-blocking)."""
        if not self._memory:
            return
        try:
            await asyncio.to_thread(self._memory.add, messages, user_id=user_id)
        except Exception as exc:
            logger.warning("mem0_add_failed", error=str(exc))

    async def search(self, query: str, limit: int | None = None, user_id: str = "default_user") -> str:
        """Return top memories as a bullet-point string, capped at max_chars (non-blocking)."""
        if not self._memory or not query:
            return ""
        effective_limit = limit if limit is not None else settings.memory_search_limit
        try:
            results = await asyncio.to_thread(
                self._memory.search, query, user_id=user_id, limit=effective_limit
            )
            memories = (
                results if isinstance(results, list) else results.get("results", [])
            )
            if not memories:
                return ""

            lines = []
            total = 0
            for m in memories:
                text = m.get("memory", "") if isinstance(m, dict) else str(m)
                if not text:
                    continue
                line = f"- {text}"
                if total + len(line) > settings.memory_max_chars:
                    break
                lines.append(line)
                total += len(line)

            return "\n".join(lines)
        except Exception as exc:
            logger.warning("mem0_search_failed", error=str(exc))
            return ""
