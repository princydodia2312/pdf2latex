"""
tests/test_pdf_type_check.py
----------------------------
Unit tests for Stage 1: pdf_type_check.run()

Strategy
--------
Tests create minimal in-memory PDFs using PyMuPDF itself, write them to
a temp file, then pass the path to run(). No external fixture files needed.

Cases covered
-------------
T1.4  born-digital PDF  → returns "born_digital"
T1.5a scanned PDF       → raises ScannedPDFError
T1.5b empty PDF         → raises ScannedPDFError
T1.5c error attributes  → ScannedPDFError carries correct pdf_path + char_count
T1.5d multi-page PDF where only later pages have text → returns "born_digital"
      (tests that the sample window covers up to 3 pages, not just page 0)
"""

from __future__ import annotations

import os
import tempfile

import fitz  # PyMuPDF
import pytest

from pdf_to_latex.stages.pdf_type_check import (
    SCANNED_CHAR_THRESHOLD,
    ScannedPDFError,
    run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf(pages: list[str]) -> str:
    """
    Create a temporary PDF with one page per string in *pages*.
    Each string is inserted as a text block on its page.
    Returns the path to the temp file (caller must delete).
    """
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text(
                fitz.Point(72, 72),  # 1-inch margin from top-left
                text,
                fontsize=12,
            )
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    doc.save(tmp.name)
    doc.close()
    return tmp.name


# ---------------------------------------------------------------------------
# T1.4 — born-digital PDF returns "born_digital"
# ---------------------------------------------------------------------------

class TestBornDigital:
    def test_single_page_with_text_returns_born_digital(self):
        path = _make_pdf(["This is a born-digital PDF with plenty of text content."])
        try:
            result = run(path)
            assert result == "born_digital"
        finally:
            os.unlink(path)

    def test_multi_page_pdf_returns_born_digital(self):
        path = _make_pdf([
            "Page one has enough text to be clearly born-digital.",
            "Page two also has content.",
            "Page three as well.",
        ])
        try:
            result = run(path)
            assert result == "born_digital"
        finally:
            os.unlink(path)

    def test_text_exactly_at_threshold_is_born_digital(self):
        # Build a string whose stripped length is exactly SCANNED_CHAR_THRESHOLD.
        text = "x" * SCANNED_CHAR_THRESHOLD
        path = _make_pdf([text])
        try:
            result = run(path)
            assert result == "born_digital"
        finally:
            os.unlink(path)

    def test_text_spread_across_pages_accumulates_correctly(self):
        # Each page has fewer chars than the threshold, but together they exceed it.
        chunk = "x" * (SCANNED_CHAR_THRESHOLD // 3 + 1)
        path = _make_pdf([chunk, chunk, chunk])
        try:
            result = run(path)
            assert result == "born_digital"
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# T1.5 — scanned / empty PDF raises ScannedPDFError
# ---------------------------------------------------------------------------

class TestScannedPDF:
    def test_empty_pdf_raises(self):
        # A PDF with one blank page (no text inserted).
        path = _make_pdf([""])
        try:
            with pytest.raises(ScannedPDFError):
                run(path)
        finally:
            os.unlink(path)

    def test_whitespace_only_page_raises(self):
        # Whitespace-only text should be stripped to zero chars.
        path = _make_pdf(["   \n\n\t  "])
        try:
            with pytest.raises(ScannedPDFError):
                run(path)
        finally:
            os.unlink(path)

    def test_text_below_threshold_raises(self):
        # A single short word — well below the threshold.
        path = _make_pdf(["Hi"])
        try:
            with pytest.raises(ScannedPDFError):
                run(path)
        finally:
            os.unlink(path)

    def test_error_carries_correct_pdf_path(self):
        path = _make_pdf([""])
        try:
            with pytest.raises(ScannedPDFError) as exc_info:
                run(path)
            assert exc_info.value.pdf_path == path
        finally:
            os.unlink(path)

    def test_error_carries_char_count(self):
        path = _make_pdf([""])
        try:
            with pytest.raises(ScannedPDFError) as exc_info:
                run(path)
            # Char count must be a non-negative integer below the threshold.
            assert isinstance(exc_info.value.char_count, int)
            assert 0 <= exc_info.value.char_count < SCANNED_CHAR_THRESHOLD
        finally:
            os.unlink(path)

    def test_error_message_mentions_path(self):
        path = _make_pdf([""])
        try:
            with pytest.raises(ScannedPDFError) as exc_info:
                run(path)
            assert path in str(exc_info.value)
        finally:
            os.unlink(path)

    def test_only_first_three_pages_are_sampled(self):
        # First 3 pages are blank; page 4 has lots of text.
        # run() should still raise because only pages 0-2 are sampled.
        lots_of_text = "x" * (SCANNED_CHAR_THRESHOLD * 10)
        path = _make_pdf(["", "", "", lots_of_text])
        try:
            with pytest.raises(ScannedPDFError):
                run(path)
        finally:
            os.unlink(path)
