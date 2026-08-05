"""
stages/labeling.py
------------------
Stage 3 of the pdf2TeX pipeline.

Assigns a section_label and confidence score to every SpanRecord using
style- and position-based heuristics only. No ML, no NLP, no external
API calls. This module is the v0 placeholder — in v1 it will be replaced
(or augmented) by a document-type classifier and an LLM-based section
classifier, both with the same run() signature.

Public API
----------
    run(spans: list[SpanRecord]) -> list[SpanRecord]

    Returns the same list with document_type, section_label, and
    confidence populated on every record. Input records are mutated
    in-place and also returned, so callers can choose either style.

Label vocabulary (v0 — document-type-agnostic)
-----------------------------------------------
    "heading_1"      Large bold text — maps to \section{}
    "heading_2"      Medium bold text — maps to \subsection{}
    "heading_3"      Slightly large or bold text — maps to \subsubsection{}
    "list_item"      Line starting with a bullet or numbered-list marker
    "centered_block" All spans in block are center-aligned
    "body"           Everything else

Label rules (applied at block granularity, first match wins)
------------------------------------------------------------
    Per-block features computed first:
        max_font_size       largest font size among spans in the block
        is_bold             True if any span in the block is bold
        is_center           True if the dominant alignment is "center"
        relative_font_size  max_font_size / median_font_size_of_document
                            (1.0 = same as the median body text)

    Rules in evaluation order:
        relative_font_size >= 1.4  AND  is_bold  → heading_1  (conf 0.85)
        relative_font_size >= 1.2  AND  is_bold  → heading_2  (conf 0.80)
        relative_font_size >= 1.1  OR   is_bold  → heading_3  (conf 0.70)
        text starts with list marker              → list_item  (conf 0.90)
        is_center                                → centered_block (conf 0.75)
        fallthrough                              → body        (conf 0.95)

    All spans in a block receive the same section_label and confidence.

Design notes
------------
- "Block" is identified by the (page, block_index) pair inherited from
  the extraction stage. All spans sharing that pair are treated as one
  semantic unit for labeling purposes.
- The median font size is computed across all spans in the document
  (not per-page) so that a small decorative font on one page doesn't
  distort the reference point.
- Confidence values are static in v0. They exist so downstream code
  (the future correction UI) can treat confidence as a first-class
  attribute from day one without a schema change.
- document_type is always set to "unknown" in v0. The architecture slot
  is present; the classifier that fills it arrives in v1.
"""

from __future__ import annotations

import re
import statistics
from itertools import groupby

from pdf_to_latex.schema import SpanRecord

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Relative font-size thresholds for heading detection.
HEADING_1_RATIO: float = 1.4
HEADING_2_RATIO: float = 1.2
HEADING_3_RATIO: float = 1.1

# Static confidence scores for each label (v0 placeholders).
CONFIDENCE: dict[str, float] = {
    "heading_1":      0.85,
    "heading_2":      0.80,
    "heading_3":      0.70,
    "list_item":      0.90,
    "centered_block": 0.75,
    "body":           0.95,
}

# Regex that matches common list-item prefixes at the start of a string:
#   - Bullet characters: • - * · ‣ ◦ ▪ ▸ ►
#   - Numbered list:     "1." "2)" "(3)" "a." "A)"
_LIST_MARKER_RE = re.compile(
    r"^(\s*"
    r"([•\-\*·‣◦▪▸►]"           # bullet characters
    r"|(\(?\d+[\.\)])"           # 1. 1) (1)
    r"|(\(?[a-zA-Z][\.\)])"      # a. a) (a) A. A)
    r")\s)"
)

# Minimum number of spans in a block for "is_center" to apply.
# Avoids labeling a single isolated centered word as centered_block
# when it could be a heading already caught by font-size rules.
_MIN_SPANS_FOR_CENTER_LABEL: int = 1  # kept permissive; rules run in order


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(spans: list[SpanRecord]) -> list[SpanRecord]:
    """
    Label every SpanRecord with a section_label and confidence score.

    Parameters
    ----------
    spans : list[SpanRecord]
        Output from Stage 2 (extraction). Each span must have text,
        bold, font_size, alignment, page, and block_index populated.

    Returns
    -------
    list[SpanRecord]
        The same list, with document_type, section_label, and confidence
        set on every record. Records are mutated in-place.
    """
    if not spans:
        return spans

    # Step 1: Set document_type = "unknown" on all records (v0).
    for span in spans:
        span.document_type = "unknown"

    # Step 2: Compute document-wide median font size.
    median_font_size = _document_median_font_size(spans)

    # Step 3: Group spans by (page, block_index) and label each block.
    # groupby requires the list to be sorted by the grouping key.
    sorted_spans = sorted(spans, key=lambda s: (s.page, s.block_index, s.line_index, s.span_index))

    for _block_key, block_iter in groupby(
        sorted_spans, key=lambda s: (s.page, s.block_index)
    ):
        block_spans = list(block_iter)
        label, confidence = _label_block(block_spans, median_font_size)
        for span in block_spans:
            span.section_label = label
            span.confidence = confidence

    return spans


# ---------------------------------------------------------------------------
# Per-block feature computation and labeling
# ---------------------------------------------------------------------------

def _document_median_font_size(spans: list[SpanRecord]) -> float:
    """
    Compute the median font size across all spans in the document.
    Falls back to 12.0 if no spans have a positive font size.
    """
    sizes = [s.font_size for s in spans if s.font_size > 0]
    if not sizes:
        return 12.0
    return statistics.median(sizes)


def compute_block_features(block_spans: list[SpanRecord], median_font_size: float) -> dict:
    """
    Compute per-block features used by the label rules.

    Returns a dict with keys:
        max_font_size       float
        is_bold             bool
        is_center           bool
        relative_font_size  float
        first_text          str   (stripped text of the first non-empty span)

    Exposed as a public function so tests can inspect features directly.
    """
    max_font_size = max((s.font_size for s in block_spans), default=0.0)
    is_bold = any(s.bold for s in block_spans)

    # "is_center": majority of spans in this block are center-aligned.
    center_count = sum(1 for s in block_spans if s.alignment == "center")
    is_center = center_count > len(block_spans) / 2

    relative_font_size = (
        max_font_size / median_font_size if median_font_size > 0 else 1.0
    )

    # First non-empty text in the block — used for list-marker detection.
    first_text = next(
        (s.text.strip() for s in block_spans if s.text.strip()), ""
    )

    return {
        "max_font_size": max_font_size,
        "is_bold": is_bold,
        "is_center": is_center,
        "relative_font_size": relative_font_size,
        "first_text": first_text,
    }


def _label_block(
    block_spans: list[SpanRecord],
    median_font_size: float,
) -> tuple[str, float]:
    """
    Apply label rules to a block and return (label, confidence).
    Rules are evaluated in order; first match wins.
    """
    f = compute_block_features(block_spans, median_font_size)
    rfz = f["relative_font_size"]

    # Rule 1 — heading_1: large AND bold
    if rfz >= HEADING_1_RATIO and f["is_bold"]:
        return "heading_1", CONFIDENCE["heading_1"]

    # Rule 2 — heading_2: medium-large AND bold
    if rfz >= HEADING_2_RATIO and f["is_bold"]:
        return "heading_2", CONFIDENCE["heading_2"]

    # Rule 3 — heading_3: slightly large OR bold
    if rfz >= HEADING_3_RATIO or f["is_bold"]:
        return "heading_3", CONFIDENCE["heading_3"]

    # Rule 4 — list_item: first text starts with a list marker
    if _LIST_MARKER_RE.match(f["first_text"]):
        return "list_item", CONFIDENCE["list_item"]

    # Rule 5 — centered_block: majority alignment is center
    if f["is_center"]:
        return "centered_block", CONFIDENCE["centered_block"]

    # Rule 6 — body: fallthrough
    return "body", CONFIDENCE["body"]
