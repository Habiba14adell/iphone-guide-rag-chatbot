
import logging
import re
import unicodedata
from collections import Counter
import pymupdf
from .layout import extract_layout, sort_by_block


logger = logging.getLogger(__name__)
FOOTER_RATIO = 0.90
SUBSECTION_RATIO = 1.18
SECTION_RATIO = 1.35
CHAPTER_RATIO = 1.80
DIAGRAM_RATIO = 0.82


def clean_text(text):
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    return re.sub(r"[^\S\n]+", " ", text).strip()


def get_lines(page):
    lines, _ = extract_layout(page, clean_text)
    return lines


def read_contents(document):
    entries, contents_pages = [], []
    for index in range(min(15, len(document))):
        text = clean_text(document[index].get_text())
        # A body paragraph can mention "Contents" without being a contents page.
        # Require its standalone heading/footer and numbered contents entries.
        has_contents_label = "Contents" in [line.strip() for line in text.splitlines()]
        has_page_entries = re.search(r"(?m)^\s*\d{1,3}[ \t]*(?:\n[ \t]*)?[A-Za-z]", text)
        if not has_contents_label or not has_page_entries:
            continue
        contents_pages.append(index + 1)
        pattern = r"(?:^|\n)\s*(\d{1,3})\s+((?:Chapter\s+\d+|Appendix\s+[A-Z]):[^\n]+)"
        for page, title in re.findall(pattern, text):
            entries.append({"printed_page": int(page), "title": clean_text(title)})
    return entries, contents_pages


def classify_block(lines, body_size):
    if any(line.get("table_row") for line in lines):
        return "table"
    text = " ".join(line["text"] for line in lines)
    if re.match(r"^(WARNING|CAUTION|Important|Note)\s*:", text, re.I):
        return "warning"
    if any(re.match(r"^\d+[.)]?\s+\D", line["text"]) for line in lines):
        return "procedure"
    if max(line["size"] for line in lines) < body_size * DIAGRAM_RATIO:
        return "diagram"
    return "paragraph"


def recover_table_rows(lines, body_size, page_height):
    # The guide's borderless tables have small bold headers and aligned columns.
    headers = sorted([line for line in lines if line["size"] < body_size
                      and "bold" in line["font"].lower()
                      and line["bbox"][1] < page_height * FOOTER_RATIO],
                     key=lambda line: (line["bbox"][1], line["bbox"][0]))
    starts = []
    for left, right in zip(headers, headers[1:]):
        if abs(left["bbox"][1] - right["bbox"][1]) < 3 and right["bbox"][0] > left["bbox"][2] + 8:
            starts.append((left, right))
    for left, right in starts:
        top = left["bbox"][1] - 1
        following_headings = [line["bbox"][1] for line in lines
                              if line["bbox"][1] > top + 4 and line["size"] >= body_size * SUBSECTION_RATIO]
        bottom = min(following_headings, default=page_height * FOOTER_RATIO)
        region = [line for line in lines if top <= line["bbox"][1] < bottom and line["size"] < body_size]
        boundary = right["bbox"][0] - 3
        anchors, seen_blocks = [], set()
        for line in region:
            if line["bbox"][0] >= boundary or line["block"] in seen_blocks:
                continue
            if any(abs(other["bbox"][1] - line["bbox"][1]) < 3 and other["bbox"][0] >= boundary for other in region):
                anchors.append(line)
                seen_blocks.add(line["block"])
        anchors.sort(key=lambda line: line["bbox"][1])
        if len(anchors) < 3:
            continue
        rows = []
        for index, anchor in enumerate(anchors):
            row_bottom = anchors[index + 1]["bbox"][1] - 1 if index + 1 < len(anchors) else bottom
            cells = [line for line in region if anchor["bbox"][1] - 1 <= line["bbox"][1] < row_bottom]
            cells.sort(key=lambda line: line["bbox"][1])
            label = " ".join(line["text"] for line in cells if line["bbox"][0] < boundary)
            description = " ".join(line["text"] for line in cells if line["bbox"][0] >= boundary)
            rows.append(dict(anchor, text=f"{label} | {description}", table_row=True,
                             block=f"table-{top}-{index}"))
        region_ids = {id(line) for line in region}
        lines = [line for line in lines if id(line) not in region_ids] + rows
    return sort_by_block(lines)


def start_section(sections, headings, chapter, title, page_number, method):
    section = {"chapter": chapter, "section": title, "blocks": []}
    sections.append(section)
    headings.append({"chapter": chapter, "section": title, "pdf_page": page_number, "method": method})
    return section


def append_paragraph(section, lines, page_info, body_size, is_legal_page):
    if not lines:
        return
    kind = "paragraph" if is_legal_page else classify_block(lines, body_size)
    separator = "\n" if kind in {"table", "procedure", "diagram"} else " "
    icons = [reference for line in lines for reference in line.get("icon_references", [])]
    section["blocks"].append({
        "text": separator.join(line["text"] for line in lines),
        "pdf_page_start": page_info["pdf_page"], "pdf_page_end": page_info["pdf_page"],
        "printed_page_start": page_info["printed_page"], "printed_page_end": page_info["printed_page"],
        "chunk_type": kind, "icon_references": icons,
    })
    lines.clear()


def get_page_issues(text, lines, body_size, corrections):
    issues = []
    if not text.strip():
        issues.append("empty_text")
    elif len(text.strip()) < 100:
        issues.append("sparse_text")
    if "\ufffd" in text or "\x00" in text:
        issues.append("replacement_or_null_characters")
    if sum(line["size"] < body_size * DIAGRAM_RATIO for line in lines) >= 4:
        issues.append("diagram_labels_check_reading_order_and_missing_icons")
    if corrections["inline_icons"]:
        issues.append("inline_icons_require_visual_reference")
    elif re.search(r"(?:tap|appears|mode)\s+[.,]", text, re.I):
        issues.append("possible_missing_inline_icon")
    return issues


def extract_pdf(pdf_path):
    logger.info("Loading PDF: %s", pdf_path)
    pages, sections, headings = [], [], []
    with pymupdf.open(pdf_path) as document:
        contents, contents_pages = read_contents(document)
        layouts = [extract_layout(page, clean_text) for page in document]
        sizes = Counter()
        for lines, corrections in layouts:
            for line in lines:
                sizes[round(line["size"], 1)] += len(line["text"])
        body_size = sizes.most_common(1)[0][0] if sizes else 10.0
        chapter, previous_chapter = "Front matter", None
        section_title, subsection, current = "", "", None

        for page_number, (page, layout) in enumerate(zip(document, layouts), start=1):
            lines, corrections = layout
            raw = page.get_text()
            numbers = [line["text"] for line in lines
                       if line["bbox"][1] > page.rect.height * FOOTER_RATIO and re.fullmatch(r"\d{1,4}", line["text"])]
            printed = int(numbers[-1]) if numbers else None
            issues = get_page_issues(raw, lines, body_size, corrections)
            record = {"pdf_page": page_number, "printed_page": printed, "text": raw,
                      "issues": issues, "excluded_reason": None, "corrections": corrections}
            pages.append(record)
            if page_number in contents_pages:
                record["excluded_reason"] = "table_of_contents"
                continue
            if page_number == 1 and contents and printed is None:
                record["excluded_reason"] = "cover"
                continue

            eligible = [entry for entry in contents if printed is not None and entry["printed_page"] <= printed]
            is_legal_page = printed is None and "All rights reserved" in raw and "trademark" in raw.lower()
            if eligible:
                chapter = eligible[-1]["title"]
            if is_legal_page:
                chapter = "Back matter"
                issues.append("copyright_page_check_column_reading_order")
                # Copyright is a two-column page: finish the left column first.
                lines.sort(key=lambda line: (line["bbox"][0] >= page.rect.width / 2, line["bbox"][1]))
            if chapter != previous_chapter:
                section_title = "Copyright and trademarks" if is_legal_page else chapter
                subsection = ""
                current = start_section(sections, headings, chapter, section_title, page_number,
                                        "legal_notice" if is_legal_page else "contents")
                previous_chapter = chapter

            if not is_legal_page:
                lines = recover_table_rows(lines, body_size, page.rect.height)
            paragraph, last_block = [], None
            for line in lines:
                if line["bbox"][1] > page.rect.height * FOOTER_RATIO:
                    continue
                if is_legal_page and line["text"] == "K":
                    continue  # Apple logo uses a nontext glyph; 'Apple Inc.' is retained.
                if line["size"] >= body_size * 3 and (line["text"].isalnum() or not any(c.isalpha() for c in line["text"])):
                    continue
                is_heading = line["size"] >= body_size * SUBSECTION_RATIO and any(c.isalpha() for c in line["text"])
                if is_heading:
                    append_paragraph(current, paragraph, record, body_size, is_legal_page)
                    if line["size"] >= body_size * CHAPTER_RATIO:
                        if not eligible:
                            chapter = line["text"]
                        section_title, subsection = line["text"], ""
                    elif line["size"] >= body_size * SECTION_RATIO:
                        section_title, subsection = line["text"], ""
                    else:
                        subsection = line["text"]
                    title = " > ".join(value for value in (section_title, subsection) if value)
                    current = start_section(sections, headings, chapter, title, page_number, "font_layout")
                else:
                    if last_block != line["block"]:
                        append_paragraph(current, paragraph, record, body_size, is_legal_page)
                    paragraph.append(line)
                last_block = line["block"]
            append_paragraph(current, paragraph, record, body_size, is_legal_page)
            record["chapter"] = chapter
            if printed is None:
                issues.append("printed_page_not_detected")

    sections = [section for section in sections if section["blocks"]]
    for page in pages:
        if page["issues"]:
            logger.warning("PDF page %s: %s", page["pdf_page"], ", ".join(page["issues"]))
    logger.info("Extracted %s pages and %s populated sections", len(pages), len(sections))
    return pages, sections, headings, contents
