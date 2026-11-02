"""Format generated answers and their retrieved PDF evidence for Chainlit."""

from ..rag.prompts import UNSUPPORTED_ANSWER

def format_pages(pages):
    return ", ".join(str(page) for page in pages) if pages else "Not available"


def format_source(chunk, rank):
    lines = [
        f"### Supporting source {rank}: {chunk.get('section', 'Untitled section')}",
        f"**Chapter:** {chunk.get('chapter', 'Not available')}",
        f"**PDF pages:** {format_pages(chunk.get('pdf_pages', []))}",
        f"**Printed pages:** {format_pages(chunk.get('printed_pages', []))}",
        f"**Document:** {chunk.get('source', 'iPhone User Guide')}",
        "",
        "**Retrieved excerpt supporting the answer**",
        "",
    ]
    if chunk.get("requires_visual_reference"):
        lines.extend(["Some controls are marked `[icon in PDF]`. View the cited PDF page to identify them.", ""])
    # Indent source text as literal content so document formatting cannot become UI markup.
    lines.extend("    " + line for line in chunk["content"].splitlines())
    return "\n\n".join(lines[:5]) + "\n\n" + "\n".join(lines[5:])


def format_answer(answer, citations):
    """Render the generated answer and PDF references supplied by retrieval metadata."""
    content = answer.strip() if isinstance(answer, str) else ""
    if not content:
        content = "I couldn't generate an answer right now. Please try again."
    if not citations or content == UNSUPPORTED_ANSWER:
        return content

    references = ["", "### Sources"]
    for citation in citations:
        rank = citation.get("source_number", "?")
        pages = format_pages(citation.get("pdf_pages", []))
        section = citation.get("section") or citation.get("chapter") or "iPhone User Guide"
        references.append(f"- Source {rank} · PDF page(s) {pages} · {section}")
    return "\n".join([content, *references])
