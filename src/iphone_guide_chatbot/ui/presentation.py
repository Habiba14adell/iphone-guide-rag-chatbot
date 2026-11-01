"""Format retrieved context for display without generating an answer."""


PENDING_MESSAGE = "**Answer generation is not configured yet.** Relevance evaluation is also pending."


def format_pages(pages):
    return ", ".join(str(page) for page in pages) if pages else "Not available"


def format_source(chunk, rank):
    lines = [
        f"### Source {rank}: {chunk.get('section', 'Untitled section')}",
        f"**Chapter:** {chunk.get('chapter', 'Not available')}",
        f"**PDF pages:** {format_pages(chunk.get('pdf_pages', []))}",
        f"**Printed pages:** {format_pages(chunk.get('printed_pages', []))}",
        f"**Document:** {chunk.get('source', 'iPhone User Guide')}",
        "",
        "**Retrieved excerpt — not a generated answer**",
        "",
    ]
    if chunk.get("requires_visual_reference"):
        lines.extend(["Some controls are marked `[icon in PDF]`. View the cited PDF page to identify them.", ""])
    # Indent the source as literal text so document formatting cannot become UI markup.
    lines.extend("    " + line for line in chunk["content"].splitlines())
    return "\n\n".join(lines[:5]) + "\n\n" + "\n".join(lines[5:])


def format_response(chunks):
    lines = [PENDING_MESSAGE, "", "### Retrieved context — not a final answer", ""]
    if not chunks:
        lines.append("No excerpts were returned for this search. You can try another question.")
        return "\n".join(lines)

    lines.extend([f"Found {len(chunks)} excerpts. Open a source to inspect its complete text.", ""])
    for rank, chunk in enumerate(chunks, start=1):
        body = chunk["content"].partition("\n\n")[2] or chunk["content"]
        preview = " ".join(body.split())
        if len(preview) > 220:
            preview = preview[:220].rsplit(" ", 1)[0] + "…"
        lines.extend([
            f"**Source {rank}** · {chunk.get('section', 'Untitled section')}",
            f"PDF pages **{format_pages(chunk.get('pdf_pages', []))}** · "
            f"Printed pages {format_pages(chunk.get('printed_pages', []))}",
            f"> {preview}", "",
        ])
    return "\n\n".join(lines)
