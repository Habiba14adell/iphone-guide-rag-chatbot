"""Configuration for PDF ingestion and local embeddings."""


import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_PATH = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_PATH / ".env")

# Existing Qdrant collection and query settings (credentials stay in .env).
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "iphone_user_guide")
VECTOR_SIZE = 384
TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))

# Gemini text generation settings.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"

# Source and output paths
PDF_PATH = "Data/iPhone User Guide 1.pdf"
OUTPUT_PATH = "artifacts/ingestion"
CACHE_PATH = ".cache/huggingface"

# Embedding model settings
MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODEL_REVISION = "main"
MODEL_LIMIT = 512
BATCH_SIZE = 32

# Chunking settings (measured with the embedding model's tokenizer)
TARGET_TOKENS = 350
MAX_TOKENS = 450
OVERLAP_TOKENS = 50


def get_config(**overrides) -> dict:
    config = {
        "model_name": MODEL_NAME,
        "model_revision": MODEL_REVISION,
        "model_limit": MODEL_LIMIT,
        "batch_size": BATCH_SIZE,
        "target_tokens": TARGET_TOKENS,
        "max_tokens": MAX_TOKENS,
        "overlap_tokens": OVERLAP_TOKENS,
    }
    for name, value in overrides.items():
        if name not in config:
            raise ValueError(f"Unknown ingestion setting: {name}")
        config[name] = value
    validate_config(config)
    return config


def validate_config(config):
    overlap = config["overlap_tokens"]
    target = config["target_tokens"]
    maximum = config["max_tokens"]
    limit = config["model_limit"]
    if not 0 <= overlap < target <= maximum <= limit:
        raise ValueError("Require 0 <= overlap < target <= maximum <= model limit")
    if config["batch_size"] < 1:
        raise ValueError("Batch size must be positive")
