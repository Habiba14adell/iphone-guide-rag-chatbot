"""Run PDF ingestion and save local files for review before using Qdrant."""

import hashlib
import json
import logging
from pathlib import Path

import numpy as np

from ..config.logging_config import setup_logging
from .chunking import create_chunks, preserve_unchanged_ids, link_notice_context
from .embeddings import generate_embeddings, load_tokenizer
from .extraction import extract_pdf
from ..config.settings import PDF_PATH, OUTPUT_PATH, SKIP_EMBEDDINGS, get_config
from .validation import inspection_text, validate_chunks


logger = logging.getLogger(__name__)


def save_jsonl(path, records):
    with path.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info("Saved %s", path)


def save_report(path, report):
    text = json.dumps(report, indent=2, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")


def save_embeddings(output_dir, chunks, vectors):
    if len(vectors) != len(chunks) or not np.isfinite(vectors).all():
        raise ValueError("Missing or nonfinite embedding vectors")
    if not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5):
        raise ValueError("Embedding vectors are not normalized")

    np.save(output_dir / "embeddings.npy", vectors, allow_pickle=False)
    embedding_ids = []
    for index, chunk in enumerate(chunks):
        embedding_ids.append({"row": index, "chunk_id": chunk["chunk_id"]})
    save_jsonl(output_dir / "embedding_ids.jsonl", embedding_ids)


def run_ingestion(pdf_path=PDF_PATH, output_dir=OUTPUT_PATH, config=None, skip_embeddings=False):
    config = get_config(**config) if config is not None else get_config()
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    previous_chunks = []
    previous_path = output_dir / "chunks.jsonl"
    if previous_path.exists():
        previous_chunks = [json.loads(line) for line in previous_path.read_text(encoding="utf-8").splitlines()]

    # Extract page text, headings, and paragraphs without losing source references.
    pages, sections, headings, contents = extract_pdf(pdf_path)
    save_jsonl(output_dir / "pages.jsonl", pages)

    # Use the same model revision for token counting and embedding.
    tokenizer = load_tokenizer(config)
    config["model_revision"] = tokenizer.init_kwargs["_commit_hash"]
    chunks = create_chunks(sections, tokenizer, config, source_hash)
    preserved_count = preserve_unchanged_ids(chunks, previous_chunks)
    link_notice_context(chunks, sections)
    for index, chunk in enumerate(chunks, start=1):
        chunk["source"] = pdf_path.name
        logger.info("Chunk %s | %s tokens | PDF pages %s-%s | %s",
                    index, chunk["token_count"], chunk["pdf_page_start"],
                    chunk["pdf_page_end"], chunk["section"])
    save_jsonl(output_dir / "chunks.jsonl", chunks)

    # Validate all chunks before passing any text to the embedding model.
    report = validate_chunks(pages, sections, chunks, tokenizer, config)
    report.update({
        "configuration": config,
        "source_sha256": source_hash,
        "headings": headings,
        "contents_chapters": contents,
        "tokenizer_revision": config["model_revision"],
        "vector_similarity": "cosine",
        "embeddings_generated": False,
        "unchanged_chunks_preserved": preserved_count,
    })
    summary = inspection_text(report, chunks)
    (output_dir / "inspection.txt").write_text(summary, encoding="utf-8")
    save_report(output_dir / "validation.json", report)
    print(summary)

    if report["errors"]:
        for error in report["errors"]:
            logger.error("Chunk validation failed: %s", error)
        raise ValueError("Chunk validation failed; inspect validation.json")
    logger.info("Validated %s pages and %s chunks; %s pages need extraction review",
                len(pages), len(chunks), len(report["problematic_pages"]))

    # Generate normalized vectors and save them locally, in chunk order.
    if not skip_embeddings:
        vectors = generate_embeddings(chunks, config, tokenizer)
        save_embeddings(output_dir, chunks, vectors)
        report.update({
            "embeddings_generated": True,
            "embedding_dimensions": int(vectors.shape[1]),
            "embedding_count": len(vectors),
            "embeddings_normalized": True,
        })
        save_report(output_dir / "validation.json", report)
        print(f"Saved {len(vectors)} embeddings ({vectors.shape[1]} dimensions) locally.")

    logger.info("Ingestion finished. Files saved to %s; no Qdrant upload performed", output_dir)
    return report


def main():
    setup_logging()
    try:
        run_ingestion(
            pdf_path=PDF_PATH,
            output_dir=OUTPUT_PATH,
            config=get_config(),
            skip_embeddings=SKIP_EMBEDDINGS,
        )
    except Exception:
        logger.exception("PDF ingestion failed")
        raise


if __name__ == "__main__":
    main()
