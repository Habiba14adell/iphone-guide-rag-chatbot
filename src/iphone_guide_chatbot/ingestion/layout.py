"""Read PDF lines without mixing captions or silently dropping inline icons."""

import re
from collections import defaultdict


ICON_MARKER = "[icon in PDF]"
POSITION_TOLERANCE = 1.0


def nearby_rectangles(first, second, tolerance=0.7):
    return (first[0] <= second[2] + tolerance and second[0] <= first[2] + tolerance
            and first[1] <= second[3] + tolerance and second[1] <= first[3] + tolerance)


def get_icon_regions(page):
    candidates = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if 1 <= rect.width <= 20 and 1 <= rect.height <= 18:
            candidates.append(list(rect))
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        if 1 <= x1 - x0 <= 20 and 1 <= y1 - y0 <= 18:
            candidates.append([x0, y0, x1, y1])

    regions = []
    for rect in candidates:
        merged = rect
        remaining = []
        for other in regions:
            if nearby_rectangles(merged, other):
                merged = [min(merged[0], other[0]), min(merged[1], other[1]),
                          max(merged[2], other[2]), max(merged[3], other[3])]
            else:
                remaining.append(other)
        regions = remaining + [merged]
    return [rect for rect in regions if 2 <= rect[2] - rect[0] <= 22 and 2 <= rect[3] - rect[1] <= 18]


def add_inline_icons(row, regions, page_number):
    if max(line["size"] for line in row) < 9:
        return row, []
    row = sorted(row, key=lambda line: line["bbox"][0])
    top = min(line["bbox"][1] for line in row)
    bottom = max(line["bbox"][3] for line in row)
    characters = [character for line in row for character in line["characters"]]
    visible = [character for character in characters if character["c"].strip()]
    references = []
    for rect in regions:
        center_y = (rect[1] + rect[3]) / 2
        if not top + 1 <= center_y <= bottom - 1:
            continue
        if any(rect[0] < character["bbox"][2] - 0.7 and rect[2] > character["bbox"][0] + 0.7 for character in visible):
            continue
        distances = [min(abs(rect[0] - character["bbox"][2]), abs(rect[2] - character["bbox"][0])) for character in visible]
        if min(distances) > 4:
            continue
        reference = {"pdf_page": page_number, "bbox": [round(value, 3) for value in rect],
                     "description": None, "status": "visual_reference_required"}
        references.append(reference)
    if not references:
        return row, []
    events = [(character["bbox"][0], character["c"]) for character in characters]
    events.extend(((ref["bbox"][0] + ref["bbox"][2]) / 2, f" {ICON_MARKER} ") for ref in references)
    events.sort(key=lambda event: event[0])
    merged = dict(row[0], text="".join(text for _, text in events))
    merged["bbox"] = [min(line["bbox"][0] for line in row), top, max(line["bbox"][2] for line in row), bottom]
    return [merged], references


def sort_by_block(lines):
    blocks = defaultdict(list)
    for line in lines:
        blocks[line["block"]].append(line)
    groups = sorted(blocks.values(), key=lambda group: (
        min(line["bbox"][1] for line in group), min(line["bbox"][0] for line in group)))
    return [line for group in groups for line in group]


def extract_layout(page, clean_text):
    lines = []
    seen = defaultdict(list)
    duplicates = 0
    for block_index, block in enumerate(page.get_text("rawdict")["blocks"]):
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            characters = [character for span in line["spans"] for character in span["chars"]]
            text = clean_text("".join(character["c"] for character in characters))
            if not text:
                continue
            bbox = list(line["bbox"])
            if any(max(abs(a-b) for a,b in zip(bbox, other)) <= POSITION_TOLERANCE for other in seen[text]):
                duplicates += 1
                continue
            seen[text].append(bbox)
            visible = [span for span in line["spans"] if any(ch["c"].strip() for ch in span["chars"])]
            size = max(span["size"] for span in visible)
            if size >= 18 and text == "·":
                continue
            text = re.sub(r"^••\s*", "• ", text)
            if text == "Appendix" and abs(line.get("dir", (1, 0))[0]) < 0.5:
                continue
            lines.append({"text": text, "bbox": bbox, "block": block_index,
                          "size": size, "font": visible[0]["font"], "icon_references": [],
                          "characters": characters})

    regions = get_icon_regions(page)
    grouped = defaultdict(list)
    for line in lines:
        grouped[line["block"]].append(line)
    result, references = [], []
    for block_index, block_lines in grouped.items():
        if all("Helvetica" in line["font"] and line["size"] < 9 for line in block_lines):
            columns = []
            for line in block_lines:
                column = next((column for column in columns
                               if abs(column[0]["bbox"][0] - line["bbox"][0]) < 10), None)
                if column is None:
                    columns.append([line])
                else:
                    column.append(line)
            for index, column in enumerate(columns):
                result.extend(dict(line, block=f"diagram-{block_index}-{index}") for line in column)
            continue
        if max(line["size"] for line in block_lines) < 9:
            result.extend(block_lines)
            continue

        rows = []
        for line in block_lines:
            row = next((row for row in rows if abs(row[0]["bbox"][1] - line["bbox"][1]) < 0.8), None)
            if row is None:
                rows.append([line])
            else:
                row.append(line)
        for row in rows:
            parts, icons = add_inline_icons(row, regions, page.number + 1)
            references.extend(icons)
            line = dict(row[0])
            line["text"] = clean_text(" ".join(part["text"] for part in parts))
            if icons:
                line["text"] = re.sub(r"\s+([,.;!?])", r"\1", line["text"])
            line["bbox"] = [min(p["bbox"][0] for p in parts), min(p["bbox"][1] for p in parts),
                            max(p["bbox"][2] for p in parts), max(p["bbox"][3] for p in parts)]
            line["icon_references"] = icons
            result.append(line)
    return sort_by_block(result), {"duplicate_lines_removed": duplicates, "inline_icons": references}
