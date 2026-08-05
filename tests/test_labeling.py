"""
tests/test_labeling.py
----------------------
Unit tests for Stage 3: labeling.run()

Strategy
--------
Tests construct SpanRecord lists directly (no PDF files needed) and
assert on the section_label and confidence assigned by run().
compute_block_features() is also tested directly for precise feature
inspection.

Cases covered
-------------
T3.6  heading_1  — relative_font_size >= 1.4 AND bold
T3.6b heading_2  — relative_font_size >= 1.2 AND bold
T3.6c heading_3  — relative_font_size >= 1.1 (not bold)
T3.6d heading_3  — bold only (font size at median)
T3.7  list_item  — various bullet and numbered-list markers
T3.8  centered_block — majority alignment is center
T3.9  body       — plain text, normal size, not bold, not centered

Additional cases:
  - document_type is always "unknown" after run()
  - confidence values match expected static values
  - all spans in a block get the same label
  - empty span list returns without error
  - compute_block_features returns correct values
  - list-marker rule does NOT fire when font-size rule matches first
  - _LIST_MARKER_RE matches expected patterns
"""

from __future__ import annotations

import pytest

from pdf_to_latex.schema import SpanRecord
from pdf_to_latex.stages.labeling import (
    CONFIDENCE,
    HEADING_1_RATIO,
    HEADING_2_RATIO,
    HEADING_3_RATIO,
    _LIST_MARKER_RE,
    compute_block_features,
    run,
)


# ---------------------------------------------------------------------------
# SpanRecord factory
# ---------------------------------------------------------------------------

def _span(
    text: str = "Sample text",
    bold: bool = False,
    italic: bool = False,
    font_size: float = 12.0,
    alignment: str = "left",
    page: int = 0,
    block_index: int = 0,
    line_index: int = 0,
    span_index: int = 0,
) -> SpanRecord:
    """Build a minimal SpanRecord for testing."""
    return SpanRecord(
        text=text,
        bold=bold,
        italic=italic,
        font_size=font_size,
        color=0,
        bbox=(72.0, 100.0, 300.0, 114.0),
        page=page,
        block_index=block_index,
        line_index=line_index,
        span_index=span_index,
        link=None,
        alignment=alignment,
    )


def _block(
    spans: list[SpanRecord],
    page: int = 0,
    block_index: int = 0,
) -> list[SpanRecord]:
    """Assign page/block_index to a list of spans."""
    for i, s in enumerate(spans):
        s.page = page
        s.block_index = block_index
        s.span_index = i
    return spans


def _with_body_context(spans: list[SpanRecord], body_block_index: int = 99) -> list[SpanRecord]:
    """
    Append enough 12pt body spans to anchor the document-wide median at 12.0.

    run() computes the median across ALL spans in the document. If a test
    builds a document with only one large-font span, that span becomes its
    own median (relative_font_size = 1.0) and font-size rules never fire.
    This helper adds 10 body spans at 12pt so the median is reliably 12.0
    regardless of what the test block contains.
    """
    body_spans = [
        _span(f"Body text line {i}", font_size=12.0, block_index=body_block_index, line_index=i)
        for i in range(10)
    ]
    for s in body_spans:
        s.page = 0
        s.block_index = body_block_index
    return spans + body_spans


# ---------------------------------------------------------------------------
# T3.6 — heading_1
# ---------------------------------------------------------------------------

class TestHeading1:
    # median = 12.0 (anchored by body context); heading_1 needs rfz >= 1.4 → font_size >= 16.8

    def test_large_bold_is_heading_1(self):
        spans = _with_body_context(_block([_span("Big Title", bold=True, font_size=20.0)]))
        run(spans)
        assert spans[0].section_label == "heading_1"

    def test_heading_1_confidence(self):
        spans = _with_body_context(_block([_span("Big Title", bold=True, font_size=20.0)]))
        run(spans)
        assert spans[0].confidence == CONFIDENCE["heading_1"]

    def test_large_not_bold_is_not_heading_1(self):
        # font_size=20 but not bold → falls through to heading_3
        spans = _with_body_context(_block([_span("Large Not Bold", bold=False, font_size=20.0)]))
        run(spans)
        assert spans[0].section_label != "heading_1"

    def test_bold_at_median_is_not_heading_1(self):
        # bold but font_size == median (12) → heading_3
        spans = _with_body_context(_block([_span("Bold Small", bold=True, font_size=12.0)]))
        run(spans)
        assert spans[0].section_label == "heading_3"

    def test_all_spans_in_block_get_heading_1(self):
        # Block with multiple spans — all should get the same label.
        block_spans = _block([
            _span("Chapter", bold=True, font_size=20.0, span_index=0),
            _span(" One",    bold=False, font_size=20.0, span_index=1),
        ])
        spans = _with_body_context(block_spans)
        run(spans)
        labels = {s.section_label for s in block_spans}
        assert labels == {"heading_1"}


# ---------------------------------------------------------------------------
# T3.6b — heading_2
# ---------------------------------------------------------------------------

class TestHeading2:
    # heading_2: rfz >= 1.2 AND bold → font_size >= 14.4

    def test_medium_large_bold_is_heading_2(self):
        spans = _with_body_context(_block([_span("Section", bold=True, font_size=15.0)]))
        run(spans)
        assert spans[0].section_label == "heading_2"

    def test_heading_2_confidence(self):
        spans = _with_body_context(_block([_span("Section", bold=True, font_size=15.0)]))
        run(spans)
        assert spans[0].confidence == CONFIDENCE["heading_2"]

    def test_heading_1_takes_precedence_over_heading_2(self):
        # font_size=20 qualifies for both; heading_1 rule fires first
        spans = _with_body_context(_block([_span("Title", bold=True, font_size=20.0)]))
        run(spans)
        assert spans[0].section_label == "heading_1"


# ---------------------------------------------------------------------------
# T3.6c/d — heading_3
# ---------------------------------------------------------------------------

class TestHeading3:
    def test_slightly_large_not_bold_is_heading_3(self):
        # rfz = 13.5/12 = 1.125 >= 1.1, not bold
        spans = _with_body_context(_block([_span("Sub-heading", bold=False, font_size=13.5)]))
        run(spans)
        assert spans[0].section_label == "heading_3"

    def test_bold_at_median_size_is_heading_3(self):
        # bold, font_size == median → rfz = 1.0 < 1.1; bold rule fires
        spans = _with_body_context(_block([_span("Bold Label", bold=True, font_size=12.0)]))
        run(spans)
        assert spans[0].section_label == "heading_3"

    def test_heading_3_confidence(self):
        spans = _with_body_context(_block([_span("Sub", bold=False, font_size=13.5)]))
        run(spans)
        assert spans[0].confidence == CONFIDENCE["heading_3"]

    def test_heading_2_takes_precedence_over_heading_3(self):
        # rfz >= 1.2 and bold → heading_2, not heading_3
        spans = _with_body_context(_block([_span("Section", bold=True, font_size=15.0)]))
        run(spans)
        assert spans[0].section_label == "heading_2"


# ---------------------------------------------------------------------------
# T3.7 — list_item
# ---------------------------------------------------------------------------

class TestListItem:
    def _list_span(self, marker: str) -> list[SpanRecord]:
        return _block([_span(f"{marker} Item text here", bold=False, font_size=12.0)])

    def test_bullet_dash(self):
        spans = self._list_span("-")
        run(spans)
        assert spans[0].section_label == "list_item"

    def test_bullet_dot(self):
        spans = self._list_span("•")
        run(spans)
        assert spans[0].section_label == "list_item"

    def test_bullet_asterisk(self):
        spans = self._list_span("*")
        run(spans)
        assert spans[0].section_label == "list_item"

    def test_bullet_middle_dot(self):
        spans = self._list_span("·")
        run(spans)
        assert spans[0].section_label == "list_item"

    def test_numbered_period(self):
        spans = self._list_span("1.")
        run(spans)
        assert spans[0].section_label == "list_item"

    def test_numbered_paren(self):
        spans = self._list_span("2)")
        run(spans)
        assert spans[0].section_label == "list_item"

    def test_numbered_wrapped_paren(self):
        spans = self._list_span("(3)")
        run(spans)
        assert spans[0].section_label == "list_item"

    def test_alpha_period(self):
        spans = self._list_span("a.")
        run(spans)
        assert spans[0].section_label == "list_item"

    def test_alpha_paren(self):
        spans = self._list_span("b)")
        run(spans)
        assert spans[0].section_label == "list_item"

    def test_list_item_confidence(self):
        spans = self._list_span("•")
        run(spans)
        assert spans[0].confidence == CONFIDENCE["list_item"]

    def test_plain_text_not_list_item(self):
        spans = _block([_span("Normal sentence without a marker.")])
        run(spans)
        assert spans[0].section_label != "list_item"

    def test_bold_list_marker_gets_heading_not_list(self):
        # If bold and at median size, heading_3 fires before list_item.
        spans = _block([_span("- Bold item", bold=True, font_size=12.0)])
        run(spans)
        assert spans[0].section_label == "heading_3"


# ---------------------------------------------------------------------------
# T3.8 — centered_block
# ---------------------------------------------------------------------------

class TestCenteredBlock:
    def test_center_aligned_block_is_centered_block(self):
        spans = _block([
            _span("Centered line", alignment="center", bold=False, font_size=12.0),
        ])
        run(spans)
        assert spans[0].section_label == "centered_block"

    def test_centered_block_confidence(self):
        spans = _block([_span("Centre", alignment="center", font_size=12.0)])
        run(spans)
        assert spans[0].confidence == CONFIDENCE["centered_block"]

    def test_majority_center_wins(self):
        spans = _block([
            _span("Line 1", alignment="center"),
            _span("Line 2", alignment="center"),
            _span("Line 3", alignment="left"),
        ])
        run(spans)
        # 2/3 centered → is_center = True
        for s in spans:
            assert s.section_label == "centered_block"

    def test_minority_center_is_not_centered_block(self):
        spans = _block([
            _span("Line 1", alignment="left"),
            _span("Line 2", alignment="left"),
            _span("Line 3", alignment="center"),
        ])
        run(spans)
        # 1/3 centered → is_center = False → falls through to body
        for s in spans:
            assert s.section_label == "body"

    def test_large_bold_center_gets_heading_not_centered_block(self):
        # heading_1 rule fires before centered_block rule
        spans = _with_body_context(_block([_span("Big", bold=True, font_size=20.0, alignment="center")]))
        run(spans)
        assert spans[0].section_label == "heading_1"


# ---------------------------------------------------------------------------
# T3.9 — body
# ---------------------------------------------------------------------------

class TestBody:
    def test_normal_text_is_body(self):
        spans = _block([_span("Normal body paragraph text here.", font_size=12.0)])
        run(spans)
        assert spans[0].section_label == "body"

    def test_body_confidence(self):
        spans = _block([_span("Body text", font_size=12.0)])
        run(spans)
        assert spans[0].confidence == CONFIDENCE["body"]

    def test_italic_normal_size_is_body(self):
        spans = _block([_span("Italic body", italic=True, bold=False, font_size=12.0)])
        run(spans)
        assert spans[0].section_label == "body"


# ---------------------------------------------------------------------------
# document_type is always "unknown" in v0
# ---------------------------------------------------------------------------

class TestDocumentType:
    def test_document_type_is_unknown(self):
        spans = _block([_span("Any text")])
        run(spans)
        assert spans[0].document_type == "unknown"

    def test_all_spans_get_unknown(self):
        spans = (
            _block([_span("Heading", bold=True, font_size=20.0)], block_index=0)
            + _block([_span("Body text")], block_index=1)
        )
        run(spans)
        assert all(s.document_type == "unknown" for s in spans)


# ---------------------------------------------------------------------------
# Multi-block document: each block gets independently labeled
# ---------------------------------------------------------------------------

class TestMultiBlock:
    def test_heading_and_body_in_same_document(self):
        heading = _block([_span("Title", bold=True, font_size=20.0)], block_index=0)
        body    = _block([_span("Some body paragraph text here.")], block_index=1)
        # _with_body_context adds 12pt spans at block_index=99 to anchor the median
        spans   = _with_body_context(heading + body)
        run(spans)

        heading_labels = {s.section_label for s in heading}
        body_labels    = {s.section_label for s in body}

        assert heading_labels == {"heading_1"}
        assert body_labels    == {"body"}

    def test_empty_span_list_returns_without_error(self):
        result = run([])
        assert result == []

    def test_returns_same_list_object(self):
        spans = _block([_span("Text")])
        result = run(spans)
        assert result is spans


# ---------------------------------------------------------------------------
# compute_block_features unit tests
# ---------------------------------------------------------------------------

class TestComputeBlockFeatures:
    def test_max_font_size(self):
        spans = [_span(font_size=10.0), _span(font_size=16.0), _span(font_size=12.0)]
        features = compute_block_features(spans, median_font_size=12.0)
        assert features["max_font_size"] == 16.0

    def test_is_bold_any_span(self):
        spans = [_span(bold=False), _span(bold=True), _span(bold=False)]
        features = compute_block_features(spans, median_font_size=12.0)
        assert features["is_bold"] is True

    def test_is_bold_false_when_no_bold(self):
        spans = [_span(bold=False), _span(bold=False)]
        features = compute_block_features(spans, median_font_size=12.0)
        assert features["is_bold"] is False

    def test_relative_font_size(self):
        spans = [_span(font_size=18.0)]
        features = compute_block_features(spans, median_font_size=12.0)
        assert features["relative_font_size"] == pytest.approx(1.5)

    def test_is_center_majority(self):
        spans = [
            _span(alignment="center"),
            _span(alignment="center"),
            _span(alignment="left"),
        ]
        features = compute_block_features(spans, median_font_size=12.0)
        assert features["is_center"] is True

    def test_is_center_false_minority(self):
        spans = [_span(alignment="left"), _span(alignment="center")]
        # 1/2 = 50%, not strictly greater than 50% → False
        features = compute_block_features(spans, median_font_size=12.0)
        assert features["is_center"] is False

    def test_first_text(self):
        spans = [_span(text="  "), _span(text="Hello world")]
        features = compute_block_features(spans, median_font_size=12.0)
        assert features["first_text"] == "Hello world"


# ---------------------------------------------------------------------------
# _LIST_MARKER_RE pattern tests
# ---------------------------------------------------------------------------

class TestListMarkerRe:
    def _matches(self, text: str) -> bool:
        return bool(_LIST_MARKER_RE.match(text))

    def test_dash(self):            assert self._matches("- item")
    def test_bullet(self):          assert self._matches("• item")
    def test_asterisk(self):        assert self._matches("* item")
    def test_triangle(self):        assert self._matches("‣ item")
    def test_numbered_dot(self):    assert self._matches("1. item")
    def test_numbered_paren(self):  assert self._matches("2) item")
    def test_wrapped_paren(self):   assert self._matches("(3) item")
    def test_alpha_dot(self):       assert self._matches("a. item")
    def test_alpha_paren(self):     assert self._matches("b) item")
    def test_no_space_after(self):  assert not self._matches("-item")
    def test_plain_text(self):      assert not self._matches("Normal text")
    def test_number_only(self):     assert not self._matches("123 text")
