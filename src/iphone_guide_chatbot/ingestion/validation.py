"""Validation and human-readable samples before any vector store upload."""

import json
import re
from collections import Counter

from .chunking import section_prefix, token_count, group_blocks, render_chunk


def validate_content_integrity(sections, chunks, tokenizer, config):
    errors, procedure_checks, notice_checks = [], [], []
    for section in sections:
        related = [chunk for chunk in chunks
                   if chunk["chapter"] == section["chapter"] and chunk["section"] == section["section"]]
        spans = [span for chunk in related for span in chunk["source_spans"]]
        for index, block in enumerate(section["blocks"]):
            matches = [chunk for chunk in related if any(span["text"] == block["text"] for span in chunk["source_spans"])]
            if not matches:
                # Oversized blocks can be distributed across several source slices.
                text = re.sub(r"\s+", "", block["text"])
                covered = set()
                for span in spans:
                    if span["pdf_page_start"] != block["pdf_page_start"]:
                        continue
                    part = re.sub(r"\s+", "", span["text"])
                    if not part:
                        continue
                    for match in re.finditer("(?=" + re.escape(part) + ")", text):
                        covered.update(range(match.start(), match.start() + len(part)))
                if len(covered) != len(text):
                    errors.append(f"Source block text missing: PDF {block['pdf_page_start']} / {section['section']}")
            if block["chunk_type"] != "warning":
                continue
            neighbors = section["blocks"][:index][::-1] + section["blocks"][index + 1:]
            context = next((item for item in neighbors if item["chunk_type"] in {"paragraph", "procedure"}), None)
            if context is None:
                status = "chapter_notice"
            elif any(any(span["text"] == context["text"] for span in chunk["source_spans"]) for chunk in matches):
                status = "same_chunk"
            elif any(chunk.get("related_context_chunk_ids") for chunk in matches):
                status = "linked_context"
            else:
                status = "missing_context"
                # Standalone tests may not run the optional relationship step.
                errors.append(f"Notice has no associated context: PDF {block['pdf_page_start']}")
            notice_checks.append({"pdf_page": block["pdf_page_start"], "section": section["section"],
                                  "status": status, "chunk_ids": [chunk["chunk_id"] for chunk in matches]})

        for group in group_blocks(section["blocks"]):
            if group[0]["chunk_type"] != "procedure":
                continue
            complete = any(all(any(span["text"] == block["text"] for span in chunk["source_spans"])
                               for block in group) for chunk in related)
            order_preserved = True
            for chunk in related:
                text_positions = [span["text"] for span in chunk["source_spans"]]
                positions = [text_positions.index(block["text"]) for block in group if block["text"] in text_positions]
                if positions != sorted(positions):
                    order_preserved = False
            if not order_preserved:
                errors.append(f"Procedure steps out of order: {section['section']}")
            fits = token_count(render_chunk(section_prefix(section), group), tokenizer) <= config["max_tokens"]
            if fits and not complete:
                errors.append(f"Procedure unnecessarily separated: {section['section']}")
            procedure_checks.append({"section": section["section"], "pdf_page": group[0]["pdf_page_start"],
                                     "kept_together": complete, "fits_maximum": fits,
                                     "order_preserved": order_preserved,
                                     "step_numbers": [int(number) for block in group
                                                      for number in re.findall(r"(?:^|\n)(\d+)[.)]?\s+\D", block["text"])]})
    return errors, procedure_checks, notice_checks


def validate_chunks(pages, sections, chunks, tokenizer, config):
    errors = []
    if not chunks:
        errors.append("No chunks were extracted")
    ids = [chunk["chunk_id"] for chunk in chunks]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate chunk IDs")
    over_limit, over_maximum = [], []
    page_map = {page["pdf_page"]: page for page in pages}
    section_keys = {(s["chapter"], s["section"]) for s in sections}
    covered_pages = set()
    for chunk in chunks:
        count = token_count(chunk["content"], tokenizer)
        if count > config["model_limit"]:
            over_limit.append(chunk["chunk_id"])
        if count > config["max_tokens"]:
            over_maximum.append(chunk["chunk_id"])
        if count != chunk["token_count"]:
            errors.append(f"Incorrect token count: {chunk['chunk_id']}")
        if not chunk["content"].startswith(section_prefix(chunk)):
            errors.append(f"Missing headings: {chunk['chunk_id']}")
        if (chunk["chapter"], chunk["section"]) not in section_keys:
            errors.append(f"Unknown section: {chunk['chunk_id']}")
        if not 1 <= chunk["pdf_page_start"] <= chunk["pdf_page_end"] <= len(pages):
            errors.append(f"Invalid PDF page range: {chunk['chunk_id']}")
        spans = chunk["source_spans"]
        for span in spans:
            covered_pages.update(range(span["pdf_page_start"], span["pdf_page_end"] + 1))
            if span["printed_page_start"] != page_map[span["pdf_page_start"]]["printed_page"]:
                errors.append(f"Incorrect printed start page: {chunk['chunk_id']}")
            if span["printed_page_end"] != page_map[span["pdf_page_end"]]["printed_page"]:
                errors.append(f"Incorrect printed end page: {chunk['chunk_id']}")
        if chunk["printed_page_start"] != spans[0]["printed_page_start"] or chunk["printed_page_end"] != spans[-1]["printed_page_end"]:
            errors.append(f"Incorrect printed page range: {chunk['chunk_id']}")
    missing_pages = [page["pdf_page"] for page in pages
                     if page["text"].strip() and not page["excluded_reason"]
                     and page["pdf_page"] not in covered_pages]
    if missing_pages:
        errors.append(f"Nonempty body pages without chunks: {missing_pages}")
    errors.extend(f"Over model limit: {value}" for value in over_limit)
    errors.extend(f"Over chunk maximum: {value}" for value in over_maximum)
    content_errors, procedure_checks, notice_checks = validate_content_integrity(sections, chunks, tokenizer, config)
    errors.extend(content_errors)
    valid_ids = set(ids)
    for chunk in chunks:
        for key in ("related_context_chunk_ids", "chapter_notice_chunk_ids"):
            if not set(chunk.get(key, [])).issubset(valid_ids):
                errors.append(f"Unknown context reference: {chunk['chunk_id']}")
    diagram_repetitions = []
    for chunk in chunks:
        for span in chunk["source_spans"]:
            lines = span["text"].splitlines()
            if span["chunk_type"] == "diagram" and any(a == b for a, b in zip(lines, lines[1:])):
                diagram_repetitions.append(chunk["chunk_id"])
    if diagram_repetitions:
        errors.append("Repeated adjacent diagram label lines")
    return {
        "total_pages": len(pages), "total_sections": len(sections), "total_chunks": len(chunks),
        "max_token_count": max((chunk["token_count"] for chunk in chunks), default=0),
        "chunks_exceeding_model_limit": over_limit,
        "chunks_exceeding_chunk_maximum": over_maximum,
        "empty_pages": [p["pdf_page"] for p in pages if not p["text"].strip()],
        "problematic_pages": [{"pdf_page": p["pdf_page"], "issues": p["issues"]}
                              for p in pages if p["issues"]],
        "excluded_pages": [{"pdf_page": p["pdf_page"], "reason": p["excluded_reason"]}
                           for p in pages if p["excluded_reason"]],
        "chunk_types": dict(Counter(c["chunk_type"] for c in chunks)),
        "forced_split_chunks": [c["chunk_id"] for c in chunks if c["forced_split"]],
        "heading_and_page_checks_passed": not errors, "errors": errors,
        "chunk_token_counts": [{"chunk_id": c["chunk_id"], "tokens": c["token_count"]}
                               for c in chunks],
        "source_text_preserved": not content_errors,
        "procedure_checks": procedure_checks,
        "notice_checks": notice_checks,
        "diagram_repetition_chunk_ids": sorted(set(diagram_repetitions)),
        "duplicate_lines_removed": sum(p.get("corrections", {}).get("duplicate_lines_removed", 0) for p in pages),
        "inline_icon_count": sum(len(p.get("corrections", {}).get("inline_icons", [])) for p in pages),
        "visual_reference_chunk_ids": [c["chunk_id"] for c in chunks if c.get("requires_visual_reference")],
        "unresolved_text_gap_chunk_ids": [c["chunk_id"] for c in chunks
                                          if re.search(r"\b(?:tap|appears|mode)\s+[,.]|\(\s*\)", c["content"], re.I)],
    }


def representative_chunks(chunks, count=10):
    if len(chunks) <= count:
        return chunks
    indices = set()
    # Include protected content and cross-page chunks as well as document coverage.
    for kind in ("procedure", "warning", "table", "diagram"):
        index = next((i for i, chunk in enumerate(chunks)
                      if kind in chunk.get("content_types", [chunk["chunk_type"]])), None)
        if index is not None:
            indices.add(index)
    crossing = next((i for i, chunk in enumerate(chunks)
                     if chunk["pdf_page_end"] > chunk["pdf_page_start"]), None)
    if crossing is not None:
        indices.add(crossing)
    for index in range(count):
        if len(indices) == count:
            break
        indices.add(round(index * (len(chunks) - 1) / (count - 1)))
    return [chunks[index] for index in sorted(indices)]


def inspection_text(report, chunks):
    lines = [
        f"Extracted pages: {report['total_pages']}",
        f"Populated sections: {report['total_sections']}",
        f"Chunks: {report['total_chunks']}",
        f"Maximum tokens (including titles and special tokens): {report['max_token_count']}",
        f"Chunks exceeding model limit: {report['chunks_exceeding_model_limit']}",
        f"Chunks exceeding chunk maximum: {report['chunks_exceeding_chunk_maximum']}",
        f"Empty pages: {report['empty_pages']}",
        f"Heading and page checks passed: {report['heading_and_page_checks_passed']}",
        f"Source block text preserved: {report['source_text_preserved']}",
        f"Duplicate painted lines removed: {report['duplicate_lines_removed']}",
        f"Repeated diagram label chunks: {report['diagram_repetition_chunk_ids']}",
        f"Inline source icons retained as visual references: {report['inline_icon_count']}",
        f"Unresolved blank text gaps: {report['unresolved_text_gap_chunk_ids']}",
        "Numbered procedure checks: " + json.dumps(report["procedure_checks"]),
        "Notice context checks: " + json.dumps(dict(Counter(note["status"] for note in report["notice_checks"]))),
        "\nPotentially problematic pages:",
        json.dumps(report["problematic_pages"], ensure_ascii=False, indent=2),
        "\nToken counts for every chunk:",
    ]
    lines.extend(f"{i + 1:04d} | {c['chunk_id']} | {c['token_count']} tokens | PDF {c['pdf_page_start']}-{c['pdf_page_end']}"
                 for i, c in enumerate(chunks))
    lines.append("\n10 representative chunks (all metadata and content):")
    lines.extend(json.dumps(chunk, ensure_ascii=False, indent=2)
                 for chunk in representative_chunks(chunks))
    lines.append("\nValidation errors: " + json.dumps(report["errors"]))
    return "\n".join(lines) + "\n"
