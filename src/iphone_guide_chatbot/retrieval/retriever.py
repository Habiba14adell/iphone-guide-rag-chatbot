import logging
import numpy as np
from qdrant_client import QdrantClient, models
from ..config import settings
from ..config.logging_config import setup_logging
from ..ingestion.embeddings import generate_embeddings, load_tokenizer


logger = logging.getLogger(__name__)


def connect_to_qdrant():
    client = None
    try:
        if not settings.QDRANT_URL or not settings.QDRANT_API_KEY:
            raise ValueError("QDRANT_URL and QDRANT_API_KEY are required")
        client = QdrantClient(
            url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY,
            timeout=30, check_compatibility=False,
        )
        info = client.get_collection(settings.COLLECTION_NAME)
        vectors = info.config.params.vectors
        if not isinstance(vectors, models.VectorParams):
            raise ValueError("Expected a collection with unnamed dense vectors")
        if vectors.size != settings.VECTOR_SIZE or vectors.distance != models.Distance.COSINE:
            raise ValueError("Collection must use 384-dimensional cosine vectors")
        logger.info("Connected to Qdrant collection '%s'", settings.COLLECTION_NAME)
        return client
    except Exception as error:
        logger.error("Qdrant connection failed (%s)", type(error).__name__)
        if client is not None:
            client.close()
        raise


def get_query_embedding(question):
    config = settings.get_config()
    tokenizer = load_tokenizer(config)
    config["model_revision"] = tokenizer.init_kwargs["_commit_hash"]

    vectors = generate_embeddings([{"content": question}], config, tokenizer)
    vector = vectors[0]
    if len(vector) != settings.VECTOR_SIZE or not np.isfinite(vector).all():
        raise ValueError("Query embedding has an invalid dimension or nonfinite values")
    return vector.tolist()


def get_page_range(source_spans, start_key, end_key):
    pages = set()
    for span in source_spans:
        start = span.get(start_key)
        end = span.get(end_key)
        if start is None or end is None:
            continue
        if not isinstance(start, int) or not isinstance(end, int) or not 1 <= start <= end:
            raise ValueError("Source span contains an invalid page range")
        pages.update(range(start, end + 1))
    return sorted(pages)


def format_result(point):
    result = dict(point.payload or {})
    if not isinstance(result.get("content"), str) or not result["content"].strip():
        raise ValueError("Retrieved chunk has no content")
    spans = result.get("source_spans")
    if not isinstance(spans, list) or not spans:
        raise ValueError("Retrieved chunk has no source spans")
    result["point_id"] = str(point.id)
    result["score"] = float(point.score)
    result["pdf_pages"] = get_page_range(spans, "pdf_page_start", "pdf_page_end")
    result["printed_pages"] = get_page_range(spans, "printed_page_start", "printed_page_end")
    if not result["pdf_pages"]:
        raise ValueError("Retrieved chunk has no physical PDF page references")
    return result


def retrieve_chunks(question: str, top_k: int | None = None) -> list[dict]:
    setup_logging()
    client = None
    try:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must be a nonempty string")
        limit = settings.TOP_K if top_k is None else top_k
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("Number of retrieved chunks must be a positive integer")

        client = connect_to_qdrant()
        query_vector = get_query_embedding(question.strip())
        points = client.query_points(
            collection_name=settings.COLLECTION_NAME, query=query_vector,
            limit=limit, with_payload=True,
        ).points
        chunks = [format_result(point) for point in points]
        logger.info("Retrieved %s chunks from '%s'", len(chunks), settings.COLLECTION_NAME)
        return chunks
    except Exception as error:
        logger.error("Semantic retrieval failed (%s)", type(error).__name__)
        raise
    finally:
        if client is not None:
            client.close()
