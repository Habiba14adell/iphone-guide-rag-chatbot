
import os
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from iphone_guide_chatbot.config.logging_config import setup_logging

load_dotenv()

logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION")

def create_collection():
    setup_logging()
    try:
        logger.info("Connecting to Qdrant to check collection '%s'", COLLECTION_NAME)
        client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY
        )

        if client.collection_exists(COLLECTION_NAME):
            logger.info("Collection '%s' already exists", COLLECTION_NAME)
            return

        logger.info("Creating collection '%s' with 384 dimensions and cosine similarity", COLLECTION_NAME)
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=384,
                distance=models.Distance.COSINE
            )
        )

        logger.info("Collection '%s' created successfully", COLLECTION_NAME)
    except Exception:
        logger.exception("Failed to prepare Qdrant collection '%s'", COLLECTION_NAME)
        raise

if __name__ == "__main__":
    create_collection()
