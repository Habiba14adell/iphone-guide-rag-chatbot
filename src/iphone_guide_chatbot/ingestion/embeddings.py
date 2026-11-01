"""Load the tokenizer and model independently of PDF processing."""

import logging
import re
from pathlib import Path

from huggingface_hub import hf_hub_download
from transformers import AutoTokenizer

from .chunking import token_count
from ..config.settings import CACHE_PATH


logger = logging.getLogger(__name__)


def load_tokenizer(config):
    # Resolve a repository revision once so ingestion remains reproducible.
    revision = config["model_revision"]
    if not Path(config["model_name"]).is_dir():
        config_path = hf_hub_download(
            config["model_name"], "config.json", revision=revision, cache_dir=CACHE_PATH
        )
        snapshot = Path(config_path).parent.name
        if re.fullmatch(r"[0-9a-f]{40}", snapshot):
            revision = snapshot
    tokenizer = AutoTokenizer.from_pretrained(
        config["model_name"], revision=revision, cache_dir=CACHE_PATH
    )
    tokenizer.init_kwargs["_commit_hash"] = revision
    if config["model_limit"] > tokenizer.model_max_length:
        raise ValueError("Configured input limit exceeds the tokenizer's model limit")
    return tokenizer


def generate_embeddings(chunks, config, tokenizer):
    # Load the model only when embeddings are requested.
    from sentence_transformers import SentenceTransformer

    logger.info("Loading embedding model %s", config["model_name"])
    model = SentenceTransformer(
        config["model_name"], revision=config["model_revision"], device="cpu", cache_folder=CACHE_PATH
    )
    limit = min(config["model_limit"], model.max_seq_length)
    texts = [chunk["content"] for chunk in chunks]
    for chunk in chunks:
        count = token_count(chunk["content"], tokenizer)
        if count > limit:
            raise ValueError(f"Chunk {chunk['chunk_id']} has {count} tokens; model allows {limit}")
    vectors = model.encode(
        texts, batch_size=config["batch_size"], normalize_embeddings=True,
        show_progress_bar=True, convert_to_numpy=True,
    )
    logger.info("Generated %s embeddings with %s dimensions", len(vectors), vectors.shape[1])
    return vectors
