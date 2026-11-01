
import os
import json
import uuid
import logging
import numpy as np

from pathlib import Path
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient, models


logging.basicConfig(level=logging.INFO,format="%(asctime)s - %(levelname)s - %(message)s")

# Configuration
load_dotenv()
DATA_PATH = Path("artifacts/ingestion/chunks.jsonl")
MODEL_NAME = "BAAI/bge-small-en-v1.5"
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION")
VECTOR_SIZE = 384
BATCH_SIZE = 64


# Connect to Qdrant Cloud
def connect_to_qdrant():

    if not QDRANT_URL or not QDRANT_API_KEY:
        raise ValueError("QDRANT_URL or QDRANT_API_KEY is missing from .env")

    client = QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY
    )

    if not client.collection_exists(COLLECTION_NAME):
        raise ValueError(
            f"Collection '{COLLECTION_NAME}' does not exist. "
            "Create it before uploading."
        )

    logging.info("Successfully connected to Qdrant Cloud")

    return client


# Load chunks from JSONL
def load_chunks(file_path):

    if not file_path.exists():
        raise FileNotFoundError(f"Chunks file not found: {file_path}")

    chunks = []

    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                chunks.append(json.loads(line))

    if not chunks:
        raise ValueError("No chunks found in the input file")

    logging.info("Successfully loaded %s chunks", len(chunks))

    return chunks


# Load embedding model
def load_embedding_model():

    model = SentenceTransformer(MODEL_NAME)

    logging.info("Embedding model loaded: %s", MODEL_NAME)

    return model


# Generate Qdrant point ID
def get_point_id(chunk_id):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))


# Upload chunks to Qdrant
def upload_chunks(client, model, chunks):

    total_uploaded = 0

    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        texts = [chunk["content"] for chunk in batch]
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False
        )

        points = []

        for chunk, vector in zip(batch, vectors):

            payload = {
                key: value
                for key, value in chunk.items()
                if key != "content"
            }

            # Store the original text with its metadata
            payload["content"] = chunk["content"]

            points.append(
                models.PointStruct(
                    id=get_point_id(chunk["chunk_id"]),
                    vector=vector.tolist(),
                    payload=payload
                )
            )

        client.upsert(collection_name=COLLECTION_NAME,points=points, wait=True)
        total_uploaded += len(points)
        logging.info("Uploaded %s / %s chunks",total_uploaded,len(chunks))

    logging.info("Successfully uploaded all %s chunks", total_uploaded)


# Verify uploaded points
def verify_upload(client):
    collection_info = client.get_collection(COLLECTION_NAME)
    logging.info("Qdrant collection: %s",COLLECTION_NAME)
    logging.info("Total points in collection: %s",collection_info.points_count)

def main():

    logging.info("Starting Qdrant ingestion")
    try:
        # Step one: connect to qdrant cloud
        client = connect_to_qdrant()
        # Step two: load chunks from jsonl file
        chunks = load_chunks(DATA_PATH)
        # Step three: load embedding model and upload chunks to qdrant
        model = load_embedding_model()
        # Step four: upload chunks to qdrant and verify upload
        upload_chunks(client, model, chunks)
        # Step five: verify upload
        verify_upload(client)
        logging.info("Ingestion completed successfully")

    except FileNotFoundError as e:
        logging.error("File error: %s", e)

    except ValueError as e:
        logging.error("Configuration or data error: %s", e)

    except Exception:
        logging.exception("An unexpected error occurred during ingestion")

    finally:
        logging.info("Qdrant ingestion process finished")

if __name__ == "__main__":
    main()
