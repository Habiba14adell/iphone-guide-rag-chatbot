"""Group related text and split long sections within the BGE token budget."""

import hashlib
import logging
import re

from ..config.settings import validate_config


logger = logging.getLogger(__name__)

# Try larger text boundaries before moving to smaller ones.
SPLIT_SEPARATORS = [r"\n\n+", r"\n", r"(?<=[.!?])\s+", r"\s+"]
PROTECTED_TYPES = {"procedure", "table", "diagram"}


def token_count(text, tokenizer) -> int:
    tokens = tokenizer.encode(
        text, add_special_tokens=True, truncation=False, verbose=False
    )
    return len(tokens)


def section_prefix(section) -> str:
    return f"Chapter: {section['chapter']}\nSection: {section['section']}\n\n"


def render_chunk(prefix, blocks) -> str:
    text = "\n\n".join(block["text"] for block in blocks)
    return prefix + text


def group_blocks(blocks):
    groups = []
    for block in blocks:
        kind = block["chunk_type"]
        if groups and kind in PROTECTED_TYPES and groups[-1][0]["chunk_type"] == kind:
            groups[-1].append(block)
        else:
            groups.append([block])

    # Keep an introduction ending with a colon beside its numbered steps.
    result = []
    for group in groups:
        if (group[0]["chunk_type"] == "procedure" and result
                and result[-1][-1]["text"].endswith(":")):
            introduction = result.pop()
            group = [dict(block, chunk_type="procedure") for block in introduction] + group
        result.append(group)
    return result


def split_long_word(text, prefix, tokenizer, config):
    parts = []
    while text:
        # Find a source-text slice that fits without decoding partial tokens.
        start, end = 1, len(text)
        while start < end:
            middle = (start + end + 1) // 2
            if token_count(prefix + text[:middle], tokenizer) <= config["target_tokens"]:
                start = middle
            else:
                end = middle - 1

        part = text[:start]
        if token_count(prefix + part, tokenizer) > config["max_tokens"]:
            raise ValueError("Section heading leaves insufficient room for source text")
        parts.append(part)
        text = text[start:]
    return parts


def split_text_recursive(text, prefix, tokenizer, config, level=0):
    if token_count(prefix + text, tokenizer) <= config["target_tokens"]:
        return [text]
    if level == len(SPLIT_SEPARATORS):
        return split_long_word(text, prefix, tokenizer, config)

    matches = list(re.finditer(SPLIT_SEPARATORS[level], text))
    if not matches:
        return split_text_recursive(text, prefix, tokenizer, config, level + 1)

    # Retain separators while splitting so no source words are removed.
    boundaries = [0] + [match.end() for match in matches] + [len(text)]
    parts = []
    for start, end in zip(boundaries, boundaries[1:]):
        if end > start:
            parts.append(text[start:end])

    result = []
    current_text = ""
    for part in parts:
        if token_count(prefix + current_text + part, tokenizer) <= config["target_tokens"]:
            current_text += part
            continue
        if current_text.strip():
            result.append(current_text.strip())
        current_text = ""
        if token_count(prefix + part, tokenizer) > config["target_tokens"]:
            result.extend(split_text_recursive(part, prefix, tokenizer, config, level + 1))
        else:
            current_text = part
    if current_text.strip():
        result.append(current_text.strip())
    return result


def split_block(block, prefix, tokenizer, config):
    if token_count(prefix + block["text"], tokenizer) <= config["max_tokens"]:
        return [block]

    logger.warning("Splitting oversized %s block on PDF page %s",
                   block["chunk_type"], block["pdf_page_start"])
    parts = split_text_recursive(block["text"], prefix, tokenizer, config)
    return [dict(block, text=part, forced_split=True) for part in parts]


def prepare_section_blocks(section, prefix, tokenizer, config):
    units = []
    for group in group_blocks(section["blocks"]):
        if token_count(render_chunk(prefix, group), tokenizer) <= config["max_tokens"]:
            units.append(group)
            continue
        # Split oversized groups between whole steps or table rows first.
        for block in group:
            for part in split_block(block, prefix, tokenizer, config):
                units.append([part])
    return units


def get_overlap(blocks, tokenizer, overlap_tokens):
    overlap = []
    remaining = overlap_tokens
    for block in reversed(blocks):
        tokens = tokenizer(block["text"], add_special_tokens=False, return_offsets_mapping=True)
        offsets = tokens["offset_mapping"]
        if len(offsets) <= remaining:
            overlap.insert(0, block)
            remaining -= len(offsets)
        else:
            # Partial paragraphs are safe for overlap; partial procedures are not.
            if block["chunk_type"] == "paragraph" and remaining:
                start = offsets[-remaining][0]
                # Token offsets may point inside a word (for example 'message').
                while start and start < len(block["text"]) and not block["text"][start - 1].isspace():
                    start += 1
                sentence = re.search(r"(?<=[.!?])\s+", block["text"][start:])
                if sentence:
                    start += sentence.end()
                if block["text"][start:].strip():
                    overlap.insert(0, dict(block, text=block["text"][start:].strip()))
            break
        if not remaining:
            break

    # Account for the separators between overlapping blocks too.
    while overlap:
        text = "\n\n".join(block["text"] for block in overlap)
        if len(tokenizer.encode(text, add_special_tokens=False)) <= overlap_tokens:
            break
        overlap.pop(0)
    return overlap


def build_chunk(section, blocks, tokenizer, config, source_hash, section_index,
                chunk_index, overlap_count):
    content = render_chunk(section_prefix(section), blocks)
    count = token_count(content, tokenizer)
    if count > min(config["max_tokens"], config["model_limit"]):
        raise ValueError("Chunk exceeds the configured token budget")

    content_types = sorted({block["chunk_type"] for block in blocks})
    identity = f"{source_hash}:{section_index}:{chunk_index}:{content}"
    source_spans = []
    for block in blocks:
        source_spans.append({
            "text": block["text"],
            "chunk_type": block["chunk_type"],
            "pdf_page_start": block["pdf_page_start"],
            "pdf_page_end": block["pdf_page_end"],
            "printed_page_start": block["printed_page_start"],
            "printed_page_end": block["printed_page_end"],
            "icon_references": block.get("icon_references", []),
        })

    return {
        "chunk_id": hashlib.sha256(identity.encode()).hexdigest(),
        "chapter": section["chapter"],
        "section": section["section"],
        "pdf_page_start": min(block["pdf_page_start"] for block in blocks),
        "pdf_page_end": max(block["pdf_page_end"] for block in blocks),
        "printed_page_start": blocks[0]["printed_page_start"],
        "printed_page_end": blocks[-1]["printed_page_end"],
        "chunk_type": content_types[0] if len(content_types) == 1 else "mixed",
        "content_types": content_types,
        "content": content,
        "token_count": count,
        "overlap_tokens": overlap_count,
        "forced_split": any(block.get("forced_split", False) for block in blocks),
        "source_spans": source_spans,
        "requires_visual_reference": any("[icon in PDF]" in block["text"] for block in blocks),
    }


def create_chunks(sections, tokenizer, config, source_hash):
    validate_config(config)
    chunks = []
    for section_index, section in enumerate(sections):
        prefix = section_prefix(section)
        if token_count(prefix, tokenizer) >= config["target_tokens"]:
            raise ValueError(f"Section title is too long: {section['section']}")

        units = prepare_section_blocks(section, prefix, tokenizer, config)
        current_blocks = []
        overlap_count = 0
        for unit in units:
            candidate = render_chunk(prefix, current_blocks + unit)
            candidate_tokens = token_count(candidate, tokenizer)
            notice_boundary = (all(block["chunk_type"] == "warning" for block in unit)
                               or (current_blocks and all(block["chunk_type"] == "warning" for block in current_blocks)))
            keep_notice_context = notice_boundary and candidate_tokens <= config["max_tokens"]
            if current_blocks and candidate_tokens > config["target_tokens"] and not keep_notice_context:
                chunk = build_chunk(section, current_blocks, tokenizer, config, source_hash,
                                    section_index, len(chunks), overlap_count)
                chunks.append(chunk)

                # Carry context forward only inside this section.
                current_blocks = get_overlap(current_blocks, tokenizer, config["overlap_tokens"])
                if token_count(render_chunk(prefix, current_blocks + unit), tokenizer) > config["max_tokens"]:
                    current_blocks = []
                overlap_text = "\n\n".join(block["text"] for block in current_blocks)
                overlap_count = len(tokenizer.encode(overlap_text, add_special_tokens=False))
            current_blocks.extend(unit)

        if current_blocks:
            chunk = build_chunk(section, current_blocks, tokenizer, config, source_hash,
                                section_index, len(chunks), overlap_count)
            chunks.append(chunk)

    logger.info("Created %s chunks from %s sections", len(chunks), len(sections))
    return chunks


def chunk_identity(chunk):
    return (chunk["chapter"], chunk["section"], chunk["pdf_page_start"], chunk["pdf_page_end"],
            chunk["printed_page_start"], chunk["printed_page_end"], chunk["content"])


def preserve_unchanged_ids(chunks, previous_chunks):
    previous_ids = {chunk_identity(chunk): chunk["chunk_id"] for chunk in previous_chunks}
    preserved = 0
    for chunk in chunks:
        identity = chunk_identity(chunk)
        if identity in previous_ids:
            chunk["chunk_id"] = previous_ids[identity]
            preserved += 1
    return preserved


def link_notice_context(chunks, sections):
    # If the hard budget separates a notice, preserve a retrievable relationship.
    for section in sections:
        section_chunks = [chunk for chunk in chunks
                          if chunk["chapter"] == section["chapter"] and chunk["section"] == section["section"]]
        if all(block["chunk_type"] == "warning" for block in section["blocks"]):
            notice_ids = [chunk["chunk_id"] for chunk in section_chunks]
            for chunk in chunks:
                if chunk["chapter"] == section["chapter"]:
                    chunk["chapter_notice_chunk_ids"] = sorted(set(chunk.get("chapter_notice_chunk_ids", []) + notice_ids))
        for index, block in enumerate(section["blocks"]):
            if block["chunk_type"] != "warning":
                continue
            neighbors = section["blocks"][:index][::-1] + section["blocks"][index + 1:]
            context = next((item for item in neighbors if item["chunk_type"] in {"paragraph", "procedure"}), None)
            if context is None:
                continue
            notice_chunks = [chunk for chunk in section_chunks
                             if any(span["text"] == block["text"] for span in chunk["source_spans"])]
            context_chunks = [chunk for chunk in section_chunks
                              if any(span["text"] == context["text"] for span in chunk["source_spans"])]
            related = {chunk["chunk_id"] for chunk in notice_chunks + context_chunks}
            for chunk in notice_chunks + context_chunks:
                existing = set(chunk.get("related_context_chunk_ids", []))
                chunk["related_context_chunk_ids"] = sorted(existing | (related - {chunk["chunk_id"]}))
