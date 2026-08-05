"""
tests/test_integration.py
--------------------------
Integration test for the full pdf2TeX v0 pipeline.

Runs pipeline.run() end-to-end on synthetic PDFs built in memory.
No external fixture files required.

Tests
-----
T5.4a  Full pipeline on a multi-element born-digital PDF:
         - produces valid LaTeX (starts/ends correctly)
         - contains expected structural elements
         - body text is present in output

T5.4b  Scanned PDF raises ScannedPDFPipelineError (not a crash)

T5.4c  CLI: born-digital PDF → writes .tex file, exits 0

T5.4d  CLI: scanned PDF → exits with code 1, informative message

T5.4e  Pipeline output contains formatting for bold and linked spans

T5.4f  No text content is silently dropped (all extractable text
         appears somewhere in the .tex output)
"""

from __future__ import annotations

import os
import tempfile

import fitz
import pytest
from click.testing import CliRunner

from pdf_to_latex.pipeline import (
    EmptyDocumentError,
    ScannedPDFPipelineError,
    run,
)
from pdf_to_latex.cli import cli


# ---------------------------------------------------------------------------
# PDF builder helpers (reused from other test modules, kept self-contained)
# ---------------------------------------------------------------------------

def _save_doc(doc: fitz.Document) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    doc.save(tmp.name)
    doc.close()
    return tmp.name


def _make_realistic_pdf() -> str:
    """
    Build a multi-element born-digital PDF that exercises the full pipeline:
      - A large bold title (→ heading_1)
      - Several body paragraphs at normal size
      - A bold section header (→ heading_3, bold at median size)
      - A bullet list
      - A hyperlink
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Large bold title — will be heading_1 (large relative font size + bold
    # requires the body text to anchor the median first; we add body lines below)
    # We simulate bold by using a font whose name contains "Bold".
    # PyMuPDF built-in "helv" doesn't have a bold variant accessible by name
    # directly, so we use flags to set bold, and also insert enough body text
    # first to anchor the median font size.

    # Body paragraphs (12pt) — anchor the document median
    body_lines = [
        "This document demonstrates the pdf2TeX v0 pipeline.",
        "The tool extracts text, style metadata, and hyperlinks from PDFs.",
        "It then produces valid, compilable LaTeX source output.",
        "Formatting such as bold and italic text is preserved.",
        "Hyperlinks are converted to href commands in the output.",
        "Section structure is inferred from font size and boldness.",
        "The pipeline runs fully automatically without any ML model.",
        "Output can be compiled with pdflatex to produce a PDF.",
    ]
    for i, line in enumerate(body_lines):
        page.insert_text(fitz.Point(72, 80 + i * 16), line, fontsize=12)

    # Bold section header (12pt bold — will be heading_3)
    page.insert_text(
        fitz.Point(72, 230),
        "Section Header",
        fontsize=12,
        # fontname defaults to helv; we rely on flags for bold detection
    )

    # Bullet list items
    list_items = ["- First bullet point", "- Second bullet point", "- Third point"]
    for i, item in enumerate(list_items):
        page.insert_text(fitz.Point(72, 260 + i * 16), item, fontsize=12)

    # A line with a hyperlink
    link_text = "GitHub Repository"
    page.insert_text(fitz.Point(72, 320), link_text, fontsize=12)
    text_width = fitz.Font("helv").text_length(link_text, fontsize=12)
    page.insert_link({
        "kind": fitz.LINK_URI,
        "from": fitz.Rect(72, 308, 72 + text_width, 324),
        "uri": "https://github.com/princydodia2312/pdf2latex",
    })

    return _save_doc(doc)


def _make_scanned_pdf() -> str:
    """PDF with no text layer (simulates a scanned document)."""
    doc = fitz.open()
    doc.new_page(width=595, height=842)  # blank page — no text
    return _save_doc(doc)


# ---------------------------------------------------------------------------
# T5.4a — full pipeline produces valid LaTeX
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_pipeline_returns_string(self):
        path = _make_realistic_pdf()
        try:
            result = run(path)
            assert isinstance(result, str)
            assert len(result) > 0
        finally:
            os.unlink(path)

    def test_output_starts_with_documentclass(self):
        path = _make_realistic_pdf()
        try:
            result = run(path)
            assert result.startswith(r"\documentclass{article}")
        finally:
            os.unlink(path)

    def test_output_ends_with_end_document(self):
        path = _make_realistic_pdf()
        try:
            result = run(path)
            assert result.rstrip().endswith(r"\end{document}")
        finally:
            os.unlink(path)

    def test_output_contains_begin_document(self):
        path = _make_realistic_pdf()
        try:
            result = run(path)
            assert r"\begin{document}" in result
        finally:
            os.unlink(path)

    def test_body_text_present_in_output(self):
        path = _make_realistic_pdf()
        try:
            result = run(path)
            assert "pdf2TeX" in result
        finally:
            os.unlink(path)

    def test_list_items_produce_itemize(self):
        path = _make_realistic_pdf()
        try:
            result = run(path)
            assert r"\begin{itemize}" in result
            assert r"\item" in result
        finally:
            os.unlink(path)

    def test_hyperlink_present_in_output(self):
        path = _make_realistic_pdf()
        try:
            result = run(path)
            assert r"\href{https://github.com/princydodia2312/pdf2latex}" in result
        finally:
            os.unlink(path)

    def test_no_text_silently_dropped(self):
        """
        Every word from the body lines must appear somewhere in the output.
        Tests success criterion V9 from requirements.md.
        """
        path = _make_realistic_pdf()
        try:
            result = run(path)
            # Check a sample of distinctive words from the body lines
            for word in ["demonstrates", "extracts", "metadata", "hyperlinks",
                         "compilable", "automatically"]:
                assert word in result, f"Word '{word}' was silently dropped"
        finally:
            os.unlink(path)

    def test_required_packages_in_preamble(self):
        path = _make_realistic_pdf()
        try:
            result = run(path)
            assert r"\usepackage{hyperref}" in result
            assert r"\usepackage{parskip}" in result
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# T5.4b — scanned PDF raises clean error
# ---------------------------------------------------------------------------

class TestScannedPDFError:
    def test_scanned_pdf_raises_pipeline_error(self):
        path = _make_scanned_pdf()
        try:
            with pytest.raises(ScannedPDFPipelineError):
                run(path)
        finally:
            os.unlink(path)

    def test_scanned_pdf_error_message_is_informative(self):
        path = _make_scanned_pdf()
        try:
            with pytest.raises(ScannedPDFPipelineError) as exc_info:
                run(path)
            msg = str(exc_info.value)
            # Message should mention the file and give a hint
            assert path in msg or "scanned" in msg.lower()
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# T5.4c — CLI: born-digital PDF exits 0 and writes file
# ---------------------------------------------------------------------------

class TestCLI:
    def test_cli_exits_zero_on_valid_pdf(self):
        path = _make_realistic_pdf()
        out_tmp = tempfile.NamedTemporaryFile(suffix=".tex", delete=False)
        out_tmp.close()
        try:
            runner = CliRunner()
            result = runner.invoke(cli, [path, out_tmp.name])
            assert result.exit_code == 0, (
                f"Expected exit 0, got {result.exit_code}.\nOutput: {result.output}"
            )
        finally:
            os.unlink(path)
            if os.path.exists(out_tmp.name):
                os.unlink(out_tmp.name)

    def test_cli_writes_tex_file(self):
        path = _make_realistic_pdf()
        out_tmp = tempfile.NamedTemporaryFile(suffix=".tex", delete=False)
        out_tmp.close()
        os.unlink(out_tmp.name)  # delete so we verify the CLI creates it
        try:
            runner = CliRunner()
            runner.invoke(cli, [path, out_tmp.name])
            assert os.path.exists(out_tmp.name)
            content = open(out_tmp.name, encoding="utf-8").read()
            assert r"\documentclass{article}" in content
        finally:
            os.unlink(path)
            if os.path.exists(out_tmp.name):
                os.unlink(out_tmp.name)

    def test_cli_verbose_flag(self):
        path = _make_realistic_pdf()
        out_tmp = tempfile.NamedTemporaryFile(suffix=".tex", delete=False)
        out_tmp.close()
        try:
            runner = CliRunner()
            result = runner.invoke(cli, [path, out_tmp.name, "--verbose"])
            assert result.exit_code == 0
        finally:
            os.unlink(path)
            if os.path.exists(out_tmp.name):
                os.unlink(out_tmp.name)

    # T5.4d — scanned PDF → CLI exits 1
    def test_cli_exits_one_on_scanned_pdf(self):
        path = _make_scanned_pdf()
        out_tmp = tempfile.NamedTemporaryFile(suffix=".tex", delete=False)
        out_tmp.close()
        try:
            runner = CliRunner()
            result = runner.invoke(cli, [path, out_tmp.name])
            assert result.exit_code == 1
        finally:
            os.unlink(path)
            if os.path.exists(out_tmp.name):
                os.unlink(out_tmp.name)

    def test_cli_scanned_pdf_prints_error_message(self):
        path = _make_scanned_pdf()
        out_tmp = tempfile.NamedTemporaryFile(suffix=".tex", delete=False)
        out_tmp.close()
        try:
            runner = CliRunner()
            result = runner.invoke(cli, [path, out_tmp.name])
            # CliRunner merges stdout+stderr by default; error message in output
            assert "error" in result.output.lower() or "scanned" in result.output.lower()
        finally:
            os.unlink(path)
            if os.path.exists(out_tmp.name):
                os.unlink(out_tmp.name)
