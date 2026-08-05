"""
stages/extraction.py
--------------------
Stage 2 of the pdf2TeX pipeline.

Extracts text, style metadata, hyperlinks, and alignment from a
born-digital PDF using PyMuPDF. Returns one SpanRecord per text span,
in document order (page → block → line → span).

Public API
----------
    run(pdf_path: str) -> list[SpanRecord]

Design notes
------------
Bold/italic detection
    PyMuPDF exposes two independent signals for each span:
      1. Font name string — e.g. "Arial-BoldMT", "TimesNewRomanPS-ItalicMT".
         Checked via substring search (case-insensitive substrings defined
         in _BOLD_KEYWORDS / _ITALIC_KEYWORDS).
      2. Flags bitfield — bit 4 (value 16) = bold, bit 1 (value 2) = italic,
         as documented in the PyMuPDF reference.
    A span is considered bold/italic if EITHER signal is positive.
    Using both signals handles fonts that encode weight in the name but
    not the flags, and vice versa (common in practice).

Hyperlink association
    page.get_links() returns link annotations with a bounding box ("from")
    and URI ("uri"). Links are matched to spans by bounding-box overlap:
    a span is considered linked if the intersection area of its bbox and the
    link's bbox is at least LINK_OVERLAP_THRESHOLD (50%) of the span's own
    area. One span can only be assigned one link (first match wins).

Alignment inference
    Computed per line (all spans on the same line share one alignment value).
    Page margins are estimated as the 10th-percentile x0 and 90th-percentile
    x1 across all lines on the page. A tolerance band of MARGIN_TOLERANCE
    points is used when comparing line edges to margins.

    Rules (evaluated in order):
      center  — line midpoint is within CENTRE_TOLERANCE of the page centre
                AND line width is less than half the text-column width
      right   — x1 is within MARGIN_TOLERANCE of the right margin
                AND x0 is more than MARGIN_TOLERANCE away from the left margin
      justified — x0 is within MARGIN_TOLERANCE of the left margin
                  AND x1 is within MARGIN_TOLERANCE of the right margin
      left    — fallthrough default

    Very short lines (width < MIN_LINE_WIDTH_FOR_JUSTIFY, e.g. the last line
    of a paragraph) are never classified as justified — that last short line
    is typically left-aligned even in a justified paragraph.
"""

from __future__ import annotations

import statistics
from typing import Literal

import fitz  # PyMuPDF

from pdf_to_latex.schema import SpanRecord

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Font-name substrings that indicate bold or italic weight.
# Checked case-insensitively against the full font name string.
_BOLD_KEYWORDS: tuple[str, ...] = ("bold", "black", "heavy", "extrabold", "semibold", "demibold")
_ITALIC_KEYWORDS: tuple[str, ...] = ("italic", "oblique", "slanted")

# PyMuPDF flags bitfield values.
_FLAG_ITALIC: int = 1 << 1   # bit 1 = 2
_FLAG_BOLD: int = 1 << 4     # bit 4 = 16

# Minimum fraction of a span's area that must overlap a link bbox for the
# span to be considered part of that hyperlink.
LINK_OVERLAP_THRESHOLD: float = 0.50

# Points of tolerance when comparing line x0/x1 to estimated page margins.
MARGIN_TOLERANCE: float = 6.0

# Points of tolerance when comparing a line's midpoint to the page centre.
CENTRE_TOLERANCE: float = 10.0

# A line narrower than this fraction of the column width is never classified
# as justified (handles short last-lines of paragraphs).
MIN_LINE_WIDTH_RATIO_FOR_JUSTIFY: float = 0.85


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(pdf_path: str) -> list[SpanRecord]:
    """
    Extract all text spans from the born-digital PDF at *pdf_path*.

    Parameters
    ----------
    pdf_path : str
        Path to the PDF file. Caller is responsible for ensuring this is a
        born-digital PDF (i.e. Stage 1 has already passed).

    Returns
    -------
    list[SpanRecord]
        One SpanRecord per text span, in document order.
        The following fields are populated:
            text, bold, italic, font_size, color, bbox,
            page, block_index, line_index, span_index,
            link, alignment
        Fields that belong to later stages
        (document_type, section_label, confidence, user_confirmed)
        are left at their dataclass defaults.
    """
    doc = fitz.open(pdf_path)
    records: list[SpanRecord] = []

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_records = _extract_page(page, page_num)
            records.extend(page_records)
    finally:
        doc.close()

    return records


# ---------------------------------------------------------------------------
# Per-page extraction
# ---------------------------------------------------------------------------

def _extract_page(page: fitz.Page, page_num: int) -> list[SpanRecord]:
    """Extract all SpanRecords from a single page."""
    page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_LIGATURES)
    links = page.get_links()
    page_width = page.rect.width

    # Collect raw spans first, then compute alignment in a second pass
    # (alignment needs all line x0/x1 values to estimate margins).
    raw_spans: list[dict] = []

    for block_idx, block in enumerate(page_dict.get("blocks", [])):
        if block.get("type") != 0:
            # type 0 = text block; type 1 = image block — skip images
            continue
        for line_idx, line in enumerate(block.get("lines", [])):
            for span_idx, span in enumerate(line.get("spans", [])):
                text = span.get("text", "")
                if not text.strip():
                    # Skip purely whitespace spans — they carry no content
                    # and would pollute alignment calculations.
                    continue
                raw_spans.append({
                    "span": span,
                    "page_num": page_num,
                    "block_idx": block_idx,
                    "line_idx": line_idx,
                    "span_idx": span_idx,
                    "line_bbox": line["bbox"],  # (x0, y0, x1, y1)
                })

    if not raw_spans:
        return []

    # Estimate page margins from all line bboxes on this page.
    line_x0s = [s["line_bbox"][0] for s in raw_spans]
    line_x1s = [s["line_bbox"][2] for s in raw_spans]
    left_margin = _percentile(line_x0s, 10)
    right_margin = _percentile(line_x1s, 90)
    column_width = right_margin - left_margin
    page_centre = page_width / 2.0

    # Build SpanRecord for each raw span.
    records: list[SpanRecord] = []
    for item in raw_spans:
        span = item["span"]
        line_bbox = item["line_bbox"]

        text: str = span["text"]
        font_name: str = span.get("font", "")
        flags: int = span.get("flags", 0)
        font_size: float = span.get("size", 0.0)
        color: int = span.get("color", 0)
        bbox: tuple[float, float, float, float] = tuple(span["bbox"])  # type: ignore[assignment]

        bold = _is_bold(font_name, flags)
        italic = _is_italic(font_name, flags)
        link = _find_link(bbox, links)
        alignment = _infer_alignment(
            line_bbox, left_margin, right_margin,
            column_width, page_centre
        )

        records.append(SpanRecord(
            text=text,
            bold=bold,
            italic=italic,
            font_size=font_size,
            color=color,
            bbox=bbox,
            page=item["page_num"],
            block_index=item["block_idx"],
            line_index=item["line_idx"],
            span_index=item["span_idx"],
            link=link,
            alignment=alignment,
        ))

    return records


# ---------------------------------------------------------------------------
# Bold / italic detection  (T2.3, T2.4)
# ---------------------------------------------------------------------------

def _is_bold(font_name: str, flags: int) -> bool:
    """Return True if font name or flags indicate bold weight."""
    name_lower = font_name.lower()
    if any(kw in name_lower for kw in _BOLD_KEYWORDS):
        return True
    return bool(flags & _FLAG_BOLD)


def _is_italic(font_name: str, flags: int) -> bool:
    """Return True if font name or flags indicate italic/oblique style."""
    name_lower = font_name.lower()
    if any(kw in name_lower for kw in _ITALIC_KEYWORDS):
        return True
    return bool(flags & _FLAG_ITALIC)


# ---------------------------------------------------------------------------
# Hyperlink association  (T2.5)
# ---------------------------------------------------------------------------

def _bbox_intersection_area(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """Return the area of intersection between two bboxes (x0,y0,x1,y1)."""
    ix0 = max(a[0], b[0])
    iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2])
    iy1 = min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def _span_area(bbox: tuple[float, float, float, float]) -> float:
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    return max(w * h, 0.0)


def _find_link(
    span_bbox: tuple[float, float, float, float],
    links: list[dict],
) -> str | None:
    """
    Return the URI of the first link annotation whose bbox overlaps
    *span_bbox* by at least LINK_OVERLAP_THRESHOLD of the span's area.
    Returns None if no such link exists.
    """
    area = _span_area(span_bbox)
    if area == 0.0:
        return None

    for link in links:
        uri = link.get("uri")
        if not uri:
            continue
        link_bbox: tuple[float, float, float, float] = tuple(link["from"])  # type: ignore[assignment]
        intersection = _bbox_intersection_area(span_bbox, link_bbox)
        if intersection / area >= LINK_OVERLAP_THRESHOLD:
            return uri

    return None


# ---------------------------------------------------------------------------
# Alignment inference  (T2.6)
# ---------------------------------------------------------------------------

def _infer_alignment(
    line_bbox: tuple[float, float, float, float],
    left_margin: float,
    right_margin: float,
    column_width: float,
    page_centre: float,
) -> Literal["left", "center", "right", "justified"]:
    """
    Infer the alignment of a line from its bounding box and page geometry.
    """
    lx0, _, lx1, _ = line_bbox
    line_width = lx1 - lx0
    line_mid = (lx0 + lx1) / 2.0

    near_left = abs(lx0 - left_margin) <= MARGIN_TOLERANCE
    near_right = abs(lx1 - right_margin) <= MARGIN_TOLERANCE
    is_short = (column_width > 0) and (
        line_width / column_width < MIN_LINE_WIDTH_RATIO_FOR_JUSTIFY
    )

    # Center: midpoint close to page centre AND line is not full-width
    if abs(line_mid - page_centre) <= CENTRE_TOLERANCE and is_short:
        return "center"

    # Right: right edge near right margin, left edge not near left margin
    if near_right and not near_left:
        return "right"

    # Justified: both edges near their respective margins, line is wide enough
    if near_left and near_right and not is_short:
        return "justified"

    return "left"


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _percentile(values: list[float], pct: int) -> float:
    """
    Return the *pct*-th percentile of *values* (0–100).
    Falls back to min/max for edge cases.
    """
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    idx = (pct / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])
