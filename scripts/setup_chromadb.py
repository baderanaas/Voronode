"""Initialize ChromaDB collections"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.vector.client import ChromaDBClient
import structlog

logger = structlog.get_logger()


def main():
    logger.info("initializing_chromadb")

    client = ChromaDBClient()

    if not client.verify_connectivity():
        logger.error("cannot_connect_to_chromadb")
        sys.exit(1)

    logger.info("chromadb_connected")
    logger.info("collections_created", collections=["contracts", "emails"])


if __name__ == "__main__":
    main()
