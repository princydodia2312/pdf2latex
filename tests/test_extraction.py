"""
tests/test_extraction.py
------------------------
Unit tests for Stage 2: extraction.run()

Strategy
--------
Tests build minimal PDFs in memory using PyMuPDF, then call run() and
inspect the returned SpanRecords. No external fixture files needed.

Cases covered
-------------
T2.7  Bold/italic flags correctly set
T2.8  Hyperlink URL correctly associated with the right span
T2.9  Alignment correctly inferred for center, justified, and left lines

Additionally tests:
  - run() returns SpanRecord instances with all required fields
  - Whitespace-only spans are not included in output
  - Multi-page PDFs produce spans from all pages with correct page numbers
  - _is_bold / _is_italic helper functions (unit-tested directly)
  - _find_link helper (unit-tested directly)
  - _infer_alignment helper (unit-tested directly)
  - _percentile helper
"""

from __future__ import annotations

import os
import tempfile

import fitz
import pytest

from pdf_to_latex.stages.extraction import (
    LINK_OVERLAP_THRESHOLD,
    MARGIN_TOLERANCE,
    _bbox_intersection_area,
    _find_link,
    _infer_alignment,
    _is_bold,
    _is_italic,
    _percentile,
    run,
)
from pdf_to_latex.schema import SpanRecord


# ---------------------------------------------------------------------------
# PDF builder helpers
# ---------------------------------------------------------------------------

def _save_doc(doc: fitz.Document) -> str:
    """Save *doc* to a temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    doc.save(tmp.name)
    doc.close()
    return tmp.name


def _make_simple_pdf(text: str, fontname: str = "helv") -> str:
    """Single-page PDF with one left-aligned text run."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    page.insert_text(fitz.Point(72, 100), text, fontname=fontname, fontsize=12)
    return _save_doc(doc)


def _make_pdf_with_link(text: str, url: str) -> str:
    """Single-page PDF with text and a hyperlink covering that text."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Insert text and get its rect
    tw = fitz.TextWriter(page.rect)
    font = fitz.Font("helv")
    tw.append(fitz.Point(72, 100), text, font=font, fontsize=12)
    tw.write_text(page)
    # Compute approximate text rect for the link annotation
    text_width = font.text_length(text, fontsize=12)
    text_rect = fitz.Rect(72, 88, 72 + text_width, 104)
    page.insert_link({"kind": fitz.LINK_URI, "from": text_rect, "uri": url})
    return _save_doc(doc)


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------

class TestIsBold:
    def test_bold_in_font_name(self):
        assert _is_bold("Arial-BoldMT", 0) is True

    def test_black_in_font_name(self):
        assert _is_bold("Helvetica-Black", 0) is True

    def test_heavy_in_font_name(self):
        assert _is_bold("Futura-Heavy", 0) is True

    def test_semibold_in_font_name(self):
        assert _is_bold("SourceSansPro-SemiBold", 0) is True

    def test_bold_flag_set(self):
        # flags bit 4 = 16
        assert _is_bold("Arial", 16) is True

    def test_not_bold(self):
        assert _is_bold("Arial", 0) is False

    def test_italic_font_is_not_bold(self):
        assert _is_bold("Arial-ItalicMT", 0) is False

    def test_case_insensitive(self):
        assert _is_bold("arial-BOLD", 0) is True


class TestIsItalic:
    def test_italic_in_font_name(self):
        assert _is_italic("Arial-ItalicMT", 0) is True

    def test_oblique_in_font_name(self):
        assert _is_italic("Helvetica-Oblique", 0) is True

    def test_italic_flag_set(self):
        # flags bit 1 = 2
        assert _is_italic("Arial", 2) is True

    def test_not_italic(self):
        assert _is_italic("Arial", 0) is False

    def test_bold_font_is_not_italic(self):
        assert _is_italic("Arial-BoldMT", 0) is False

    def test_case_insensitive(self):
        assert _is_italic("times-ITALIC", 0) is True


class TestBboxIntersection:
    def test_full_overlap(self):
        a = (0.0, 0.0, 10.0, 10.0)
        assert _bbox_intersection_area(a, a) == pytest.approx(100.0)

    def test_no_overlap(self):
        a = (0.0, 0.0, 5.0, 5.0)
        b = (10.0, 10.0, 20.0, 20.0)
        assert _bbox_intersection_area(a, b) == 0.0

    def test_partial_overlap(self):
        a = (0.0, 0.0, 10.0, 10.0)
        b = (5.0, 5.0, 15.0, 15.0)
        assert _bbox_intersection_area(a, b) == pytest.approx(25.0)

    def test_adjacent_boxes_no_overlap(self):
        a = (0.0, 0.0, 5.0, 5.0)
        b = (5.0, 0.0, 10.0, 5.0)
        assert _bbox_intersection_area(a, b) == 0.0


class TestFindLink:
    def test_overlapping_link_returns_uri(self):
        span_bbox = (72.0, 88.0, 200.0, 104.0)
        links = [{"uri": "https://example.com", "from": fitz.Rect(72, 88, 200, 104)}]
        assert _find_link(span_bbox, links) == "https://example.com"

    def test_non_overlapping_link_returns_none(self):
        span_bbox = (72.0, 88.0, 200.0, 104.0)
        links = [{"uri": "https://example.com", "from": fitz.Rect(300, 300, 400, 320)}]
        assert _find_link(span_bbox, links) is None

    def test_link_without_uri_skipped(self):
        span_bbox = (72.0, 88.0, 200.0, 104.0)
        links = [{"from": fitz.Rect(72, 88, 200, 104)}]  # no "uri" key
        assert _find_link(span_bbox, links) is None

    def test_first_matching_link_wins(self):
        span_bbox = (72.0, 88.0, 200.0, 104.0)
        links = [
            {"uri": "https://first.com", "from": fitz.Rect(72, 88, 200, 104)},
            {"uri": "https://second.com", "from": fitz.Rect(72, 88, 200, 104)},
        ]
        assert _find_link(span_bbox, links) == "https://first.com"

    def test_below_threshold_returns_none(self):
        # Span is large; link covers only a tiny corner — below 50% threshold
        span_bbox = (0.0, 0.0, 100.0, 100.0)  # area = 10000
        # intersection = 5*5 = 25 → 0.25% of span area → below threshold
        links = [{"uri": "https://example.com", "from": fitz.Rect(95, 95, 100, 100)}]
        assert _find_link(span_bbox, links) is None


class TestInferAlignment:
    """Tests for _infer_alignment with explicit geometry."""

    # Page: width=595, margins left=72, right=523, column=451, centre=297.5

    LEFT_MARGIN = 72.0
    RIGHT_MARGIN = 523.0
    COLUMN_WIDTH = RIGHT_MARGIN - LEFT_MARGIN  # 451
    PAGE_CENTRE = 595.0 / 2  # 297.5

    def _align(self, lx0: float, lx1: float) -> str:
        line_bbox = (lx0, 100.0, lx1, 112.0)
        return _infer_alignment(
            line_bbox, self.LEFT_MARGIN, self.RIGHT_MARGIN,
            self.COLUMN_WIDTH, self.PAGE_CENTRE
        )

    def test_justified_full_width_line(self):
        # Spans full column — justified
        assert self._align(72.0, 523.0) == "justified"

    def test_left_aligned_partial_line(self):
        # Starts at left margin, ends well before right margin, not centred
        assert self._align(72.0, 200.0) == "left"

    def test_centered_line(self):
        # Short line centred around page_centre=297.5
        # lx0=200, lx1=395 → mid=297.5, width=195 < 85% of 451=383
        assert self._align(200.0, 395.0) == "center"

    def test_right_aligned_line(self):
        # Right edge at right margin, left edge far from left margin
        assert self._align(350.0, 523.0) == "right"

    def test_short_last_paragraph_line_is_left_not_justified(self):
        # Starts at left margin but too short to be justified
        assert self._align(72.0, 250.0) == "left"


class TestPercentile:
    def test_median_of_odd_list(self):
        assert _percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50) == pytest.approx(3.0)

    def test_10th_percentile(self):
        vals = list(range(1, 11))  # 1..10
        result = _percentile([float(v) for v in vals], 10)
        assert result == pytest.approx(1.9)

    def test_90th_percentile(self):
        vals = list(range(1, 11))
        result = _percentile([float(v) for v in vals], 90)
        assert result == pytest.approx(9.1)

    def test_single_value(self):
        assert _percentile([42.0], 50) == pytest.approx(42.0)

    def test_empty_returns_zero(self):
        assert _percentile([], 50) == 0.0


# ---------------------------------------------------------------------------
# T2.7 — Bold / italic detection via run()
# ---------------------------------------------------------------------------

class TestBoldItalicViaRun:
    def test_plain_text_not_bold_not_italic(self):
        path = _make_simple_pdf("Hello world", fontname="helv")
        try:
            records = run(path)
            assert len(records) > 0
            for r in records:
                # helv (Helvetica) is not bold or italic
                assert r.bold is False
                assert r.italic is False
        finally:
            os.unlink(path)

    def test_run_returns_span_records(self):
        path = _make_simple_pdf("Test text")
        try:
            records = run(path)
            assert all(isinstance(r, SpanRecord) for r in records)
        finally:
            os.unlink(path)

    def test_run_populates_required_fields(self):
        path = _make_simple_pdf("Test text")
        try:
            records = run(path)
            assert len(records) > 0
            r = records[0]
            assert isinstance(r.text, str) and r.text.strip()
            assert isinstance(r.font_size, float) and r.font_size > 0
            assert isinstance(r.bbox, tuple) and len(r.bbox) == 4
            assert r.page == 0
            assert r.alignment in ("left", "center", "right", "justified")
        finally:
            os.unlink(path)

    def test_whitespace_only_spans_excluded(self):
        path = _make_simple_pdf("   \n   ")
        try:
            records = run(path)
            # Any returned records must have non-empty stripped text
            for r in records:
                assert r.text.strip() != ""
        finally:
            os.unlink(path)

    def test_multi_page_page_numbers(self):
        doc = fitz.open()
        for i in range(3):
            page = doc.new_page(width=595, height=842)
            page.insert_text(
                fitz.Point(72, 100),
                f"Page {i} content with enough text to be found",
                fontsize=12,
            )
        path = _save_doc(doc)
        try:
            records = run(path)
            pages_seen = {r.page for r in records}
            assert pages_seen == {0, 1, 2}
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# T2.8 — Hyperlink association via run()
# ---------------------------------------------------------------------------

class TestHyperlinkViaRun:
    def test_linked_span_has_correct_url(self):
        url = "https://github.com/princydodia2312"
        path = _make_pdf_with_link("GitHub", url)
        try:
            records = run(path)
            linked = [r for r in records if r.link is not None]
            assert len(linked) > 0, "Expected at least one linked span"
            assert all(r.link == url for r in linked)
        finally:
            os.unlink(path)

    def test_non_linked_text_has_null_link(self):
        path = _make_simple_pdf("No links here at all")
        try:
            records = run(path)
            assert all(r.link is None for r in records)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# T2.9 — Alignment inference via run()
# ---------------------------------------------------------------------------

class TestAlignmentViaRun:
    def _make_alignment_pdf(self) -> str:
        """
        Build a PDF with multiple lines to exercise alignment detection.

        Uses insert_text (point-based) so text is always written regardless
        of rect size. We place spans at x positions that our _infer_alignment
        logic will classify correctly given the page geometry (width=595,
        left_margin≈72, right_margin≈523, centre≈297.5).
        """
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)

        # Line 1: Several left-aligned lines to anchor the margin estimates.
        # These fill most of the column so the 10th/90th percentile margins
        # land near 72 and 523 respectively.
        for y, text in [
            (80,  "Left body line one spanning most of the text column width ok."),
            (96,  "Left body line two also spanning most of the column here ok."),
            (112, "Left body line three spanning most of the text column again."),
            (128, "Left body line four to further anchor the margin estimates ok."),
            (144, "Left body line five extra line to stabilise percentile values."),
        ]:
            page.insert_text(fitz.Point(72, y), text, fontsize=10)

        # Line 6: A short centered line — we insert at x=230 so the span
        # bbox midpoint lands near the page centre (297.5).
        page.insert_text(fitz.Point(230, 170), "Centre", fontsize=14)

        return _save_doc(doc)

    def test_alignment_values_are_valid(self):
        path = self._make_alignment_pdf()
        try:
            records = run(path)
            valid = {"left", "center", "right", "justified"}
            for r in records:
                assert r.alignment in valid, f"Invalid alignment: {r.alignment!r}"
        finally:
            os.unlink(path)

    def test_all_spans_have_alignment(self):
        path = self._make_alignment_pdf()
        try:
            records = run(path)
            assert len(records) > 0
            assert all(r.alignment is not None for r in records)
        finally:
            os.unlink(path)
