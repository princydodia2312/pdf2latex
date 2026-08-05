"""
schema.py
---------
Defines SpanRecord — the shared data contract between all pipeline stages.

Every text span extracted from a PDF becomes a SpanRecord. Fields are
populated incrementally as the record passes through the pipeline:

  Stage 2 (extraction)  → text, style, bbox, link, alignment
  Stage 3 (labeling)    → document_type, section_label, confidence
  Stage 6 (correction)  → user_confirmed  [v1+, defaults to False in v0]

This file has NO imports from other project modules by design.
It is the foundation all other modules depend on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class SpanRecord:
    # ------------------------------------------------------------------
    # Set by Stage 2: Extraction
    # ------------------------------------------------------------------

    text: str
    """Raw text content of this span."""

    bold: bool
    """True if the span's font is bold (inferred from font name + flags bitfield)."""

    italic: bool
    """True if the span's font is italic (inferred from font name + flags bitfield)."""

    font_size: float
    """Font size in points."""

    color: int
    """Font color as a packed RGB integer (e.g. 0xFF0000 = red)."""

    bbox: tuple[float, float, float, float]
    """Bounding box (x0, y0, x1, y1) in points, origin top-left."""

    page: int
    """0-indexed page number this span appears on."""

    block_index: int
    """Index of the block within the page (from PyMuPDF's dict output)."""

    line_index: int
    """Index of the line within the block."""

    span_index: int
    """Index of the span within the line."""

    link: str | None
    """Hyperlink URL if this span is covered by a link annotation, else None."""

    alignment: Literal["left", "center", "right", "justified"]
    """
    Text alignment inferred from the span's line position relative to page margins.
    All spans on the same line share the same alignment value.
    """

    # ------------------------------------------------------------------
    # Set by Stage 3: Labeling
    # (heuristic rules in v0; replaced by classifier output in v1+)
    # ------------------------------------------------------------------

    document_type: str = "unknown"
    """
    Detected document type: "resume", "report", "article", or "unknown".
    Always "unknown" in v0 (no classifier yet).
    """

    section_label: str = "body"
    """
    Semantic role of this span's block:
      "heading_1", "heading_2", "heading_3",
      "list_item", "centered_block", "body"

    All spans within the same block share the same section_label.
    Label vocabulary is document-type-specific in v1+; generic in v0.
    """

    confidence: float = 0.0
    """
    Confidence score for the section_label assignment (0.0–1.0).
    Static placeholder values in v0 (see labeling.py).
    Real classifier scores in v1+.
    Used by the correction UI (v1+) to decide what to surface for review.
    """

    # ------------------------------------------------------------------
    # Set by Stage 6: Correction  [v1+ only]
    # ------------------------------------------------------------------

    user_confirmed: bool = False
    """
    True if the user has reviewed and confirmed (or corrected) this span's
    section_label in the correction UI.
    Defaults to False. In v0, the correction step does not exist —
    the assembly stage treats all records as implicitly confirmed.
    """
