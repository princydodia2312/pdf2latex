"""
tests/test_assembly.py
-----------------------
Unit tests for Stage 4: assembly.run(), escape_latex(), format_span()
and the article template helpers.

Cases covered
-------------
T4.7   bold span         → \\textbf{...}
T4.8   italic span       → \\textit{...}
T4.9   linked span       → \\href{url}{text}
T4.10  bold+italic+link  → \\href{url}{\\textbf{\\textit{...}}}
T4.11  special chars escaped before wrapping
T4.12  consecutive list items → single itemize block
T4.13  complete output starts with \\documentclass{article}
       and ends with \\end{document}

Additional cases:
  - plain span (no formatting) → raw escaped text
  - whitespace-only span → empty string
  - italic-only span → \\textit{...} without \\textbf
  - bold+italic (no link) → \\textbf{\\textit{...}}
  - each special character is escaped correctly
  - backslash escaped first (no double-escaping)
  - heading labels → \\section, \\subsection, \\subsubsection
  - centered_block → \\begin{center}...\\end{center}
  - body blocks separated by blank lines
  - non-consecutive list_item blocks each get their own itemize
  - _strip_list_marker removes leading markers
  - preamble and postamble content
  - empty spans list → still valid LaTeX document
"""

from __future__ import annotations

import pytest

from pdf_to_latex.schema import SpanRecord
from pdf_to_latex.stages.assembly import (
    _group_into_blocks,
    escape_latex,
    format_span,
    run,
)
from pdf_to_latex.stages.templates.article import (
    _strip_list_marker,
    preamble,
    postamble,
    render_blocks,
)


# ---------------------------------------------------------------------------
# SpanRecord factory
# ---------------------------------------------------------------------------

def _span(
    text: str = "Hello",
    bold: bool = False,
    italic: bool = False,
    link: str | None = None,
    section_label: str = "body",
    page: int = 0,
    block_index: int = 0,
    line_index: int = 0,
    span_index: int = 0,
) -> SpanRecord:
    return SpanRecord(
        text=text,
        bold=bold,
        italic=italic,
        font_size=12.0,
        color=0,
        bbox=(72.0, 100.0, 300.0, 114.0),
        page=page,
        block_index=block_index,
        line_index=line_index,
        span_index=span_index,
        link=link,
        alignment="left",
        section_label=section_label,
    )


def _block_spans(
    label: str,
    text: str = "Content",
    bold: bool = False,
    italic: bool = False,
    link: str | None = None,
    block_index: int = 0,
) -> list[SpanRecord]:
    return [_span(text, bold=bold, italic=italic, link=link,
                  section_label=label, block_index=block_index)]


# ---------------------------------------------------------------------------
# T4.11 — escape_latex
# ---------------------------------------------------------------------------

class TestEscapeLatex:
    def test_ampersand(self):
        assert escape_latex("a & b") == r"a \& b"

    def test_percent(self):
        assert escape_latex("100%") == r"100\%"

    def test_dollar(self):
        assert escape_latex("$5") == r"\$5"

    def test_hash(self):
        assert escape_latex("#1") == r"\#1"

    def test_underscore(self):
        assert escape_latex("a_b") == r"a\_b"

    def test_open_brace(self):
        assert escape_latex("{") == r"\{"

    def test_close_brace(self):
        assert escape_latex("}") == r"\}"

    def test_tilde(self):
        assert escape_latex("~") == r"\textasciitilde{}"

    def test_caret(self):
        assert escape_latex("^") == r"\textasciicircum{}"

    def test_backslash(self):
        # A backslash becomes \textbackslash{} — the {} are literal braces
        # in the output, not escaped, because braces are processed first.
        assert escape_latex("\\") == r"\textbackslash{}"

    def test_backslash_not_double_escaped(self):
        # Braces are escaped first, then \ -> \textbackslash{}.
        # The {} in \textbackslash{} must NOT be re-escaped to \{\}.
        result = escape_latex("\\")
        assert result == r"\textbackslash{}"
        # Only one backslash in the output (the one before "textbackslash")
        assert result == "\\textbackslash{}"

    def test_multiple_specials_in_one_string(self):
        result = escape_latex("100% & $5")
        assert r"\%" in result
        assert r"\&" in result
        assert r"\$" in result

    def test_plain_text_unchanged(self):
        assert escape_latex("Hello world") == "Hello world"

    def test_empty_string(self):
        assert escape_latex("") == ""


# ---------------------------------------------------------------------------
# T4.7 — bold span
# ---------------------------------------------------------------------------

class TestFormatSpanBold:
    def test_bold_wraps_textbf(self):
        s = _span("Hello", bold=True)
        assert format_span(s) == r"\textbf{Hello}"

    def test_non_bold_no_textbf(self):
        s = _span("Hello", bold=False)
        assert r"\textbf" not in format_span(s)

    def test_bold_with_special_char(self):
        s = _span("100%", bold=True)
        result = format_span(s)
        assert result == r"\textbf{100\%}"


# ---------------------------------------------------------------------------
# T4.8 — italic span
# ---------------------------------------------------------------------------

class TestFormatSpanItalic:
    def test_italic_wraps_textit(self):
        s = _span("Hello", italic=True)
        assert format_span(s) == r"\textit{Hello}"

    def test_non_italic_no_textit(self):
        s = _span("Hello", italic=False)
        assert r"\textit" not in format_span(s)

    def test_italic_with_special_char(self):
        s = _span("a_b", italic=True)
        result = format_span(s)
        assert result == r"\textit{a\_b}"


# ---------------------------------------------------------------------------
# T4.9 — linked span
# ---------------------------------------------------------------------------

class TestFormatSpanLink:
    def test_link_wraps_href(self):
        s = _span("GitHub", link="https://github.com")
        result = format_span(s)
        assert result == r"\href{https://github.com}{GitHub}"

    def test_no_link_no_href(self):
        s = _span("GitHub", link=None)
        assert r"\href" not in format_span(s)

    def test_link_url_percent_escaped(self):
        s = _span("Link", link="https://example.com/path?a=1%20b")
        result = format_span(s)
        assert r"\%" in result
        assert "20b" in result   # rest of URL preserved


# ---------------------------------------------------------------------------
# T4.10 — bold + italic + link nesting order
# ---------------------------------------------------------------------------

class TestFormatSpanCombined:
    def test_bold_italic_is_textbf_textit(self):
        s = _span("Hi", bold=True, italic=True)
        assert format_span(s) == r"\textbf{\textit{Hi}}"

    def test_bold_italic_link_nesting(self):
        # Expected: \href{url}{\textbf{\textit{text}}}
        s = _span("Hi", bold=True, italic=True, link="https://example.com")
        result = format_span(s)
        assert result == r"\href{https://example.com}{\textbf{\textit{Hi}}}"

    def test_bold_link_no_italic(self):
        s = _span("Hi", bold=True, italic=False, link="https://example.com")
        result = format_span(s)
        assert result == r"\href{https://example.com}{\textbf{Hi}}"

    def test_italic_link_no_bold(self):
        s = _span("Hi", bold=False, italic=True, link="https://example.com")
        result = format_span(s)
        assert result == r"\href{https://example.com}{\textit{Hi}}"

    def test_plain_span_no_wrappers(self):
        s = _span("Hello")
        assert format_span(s) == "Hello"

    def test_whitespace_only_span_returns_empty(self):
        s = _span("   ")
        assert format_span(s) == ""

    def test_special_char_escaped_inside_bold(self):
        s = _span("a & b", bold=True)
        assert format_span(s) == r"\textbf{a \& b}"


# ---------------------------------------------------------------------------
# T4.12 — consecutive list items → single itemize
# ---------------------------------------------------------------------------

class TestListItemRendering:
    def _make_list_blocks(self) -> list[list[SpanRecord]]:
        return [
            [_span("- First item", section_label="list_item", block_index=0)],
            [_span("- Second item", section_label="list_item", block_index=1)],
            [_span("- Third item", section_label="list_item", block_index=2)],
        ]

    def test_consecutive_list_items_one_itemize(self):
        blocks = self._make_list_blocks()
        result = render_blocks(blocks, format_span)
        assert result.count(r"\begin{itemize}") == 1
        assert result.count(r"\end{itemize}") == 1

    def test_all_items_present(self):
        blocks = self._make_list_blocks()
        result = render_blocks(blocks, format_span)
        assert r"\item" in result
        assert result.count(r"\item") == 3

    def test_list_markers_stripped_from_item_text(self):
        blocks = [[_span("• Bullet item", section_label="list_item", block_index=0)]]
        result = render_blocks(blocks, format_span)
        # The bullet character should not appear in the output
        assert "•" not in result
        assert "Bullet item" in result

    def test_non_consecutive_list_items_get_separate_itemize(self):
        blocks = [
            [_span("- Item one", section_label="list_item", block_index=0)],
            [_span("Body text here.", section_label="body", block_index=1)],
            [_span("- Item two", section_label="list_item", block_index=2)],
        ]
        result = render_blocks(blocks, format_span)
        assert result.count(r"\begin{itemize}") == 2
        assert result.count(r"\end{itemize}") == 2


# ---------------------------------------------------------------------------
# Heading, centered_block, body rendering
# ---------------------------------------------------------------------------

class TestBlockRendering:
    def test_heading_1_becomes_section(self):
        blocks = [_block_spans("heading_1", "Introduction")]
        result = render_blocks(blocks, format_span)
        assert r"\section{Introduction}" in result

    def test_heading_2_becomes_subsection(self):
        blocks = [_block_spans("heading_2", "Methods")]
        result = render_blocks(blocks, format_span)
        assert r"\subsection{Methods}" in result

    def test_heading_3_becomes_subsubsection(self):
        blocks = [_block_spans("heading_3", "Details")]
        result = render_blocks(blocks, format_span)
        assert r"\subsubsection{Details}" in result

    def test_centered_block_wrapped_in_center_env(self):
        blocks = [_block_spans("centered_block", "Centered text")]
        result = render_blocks(blocks, format_span)
        assert r"\begin{center}" in result
        assert r"\end{center}" in result
        assert "Centered text" in result

    def test_body_is_bare_text(self):
        blocks = [_block_spans("body", "Just some paragraph text.")]
        result = render_blocks(blocks, format_span)
        assert "Just some paragraph text." in result
        assert r"\section" not in result
        assert r"\begin{center}" not in result

    def test_table_omitted_comment_emitted(self):
        blocks = [_block_spans("table_omitted", "table data")]
        result = render_blocks(blocks, format_span)
        assert "table omitted" in result
        assert "table data" not in result

    def test_body_blocks_separated_by_blank_line(self):
        blocks = [
            _block_spans("body", "Para one.", block_index=0),
            _block_spans("body", "Para two.", block_index=1),
        ]
        result = render_blocks(blocks, format_span)
        # There should be an empty line between the two paragraphs
        assert "\n\n" in result


# ---------------------------------------------------------------------------
# T4.13 — complete document structure via run()
# ---------------------------------------------------------------------------

class TestRunOutput:
    def _simple_doc(self) -> list[SpanRecord]:
        return [
            _span("Title", bold=True, section_label="heading_1", block_index=0),
            _span("Body paragraph text here.", section_label="body", block_index=1),
        ]

    def test_output_starts_with_documentclass(self):
        result = run(self._simple_doc())
        assert result.startswith(r"\documentclass{article}")

    def test_output_ends_with_end_document(self):
        result = run(self._simple_doc())
        assert result.rstrip().endswith(r"\end{document}")

    def test_output_contains_begin_document(self):
        result = run(self._simple_doc())
        assert r"\begin{document}" in result

    def test_preamble_contains_required_packages(self):
        result = run(self._simple_doc())
        assert r"\usepackage{hyperref}" in result
        assert r"\usepackage{parskip}" in result
        assert r"\usepackage[utf8]{inputenc}" in result
        assert r"\usepackage[T1]{fontenc}" in result

    def test_empty_spans_still_valid_document(self):
        result = run([])
        assert r"\documentclass{article}" in result
        assert r"\begin{document}" in result
        assert r"\end{document}" in result

    def test_bold_span_in_full_document(self):
        spans = [_span("Bold text", bold=True, section_label="body", block_index=0)]
        result = run(spans)
        assert r"\textbf{Bold text}" in result

    def test_linked_span_in_full_document(self):
        spans = [_span("Link", link="https://example.com", section_label="body")]
        result = run(spans)
        assert r"\href{https://example.com}{Link}" in result

    def test_heading_in_full_document(self):
        # span is not bold — heading content should be plain text
        spans = [_span("Chapter One", bold=False, section_label="heading_1")]
        result = run(spans)
        assert r"\section{Chapter One}" in result

    def test_bold_heading_in_full_document(self):
        # span is bold — heading content should be wrapped in \textbf
        spans = [_span("Chapter One", bold=True, section_label="heading_1")]
        result = run(spans)
        assert r"\section{\textbf{Chapter One}}" in result

    def test_list_in_full_document(self):
        spans = [
            _span("- Item A", section_label="list_item", block_index=0),
            _span("- Item B", section_label="list_item", block_index=1),
        ]
        result = run(spans)
        assert r"\begin{itemize}" in result
        assert result.count(r"\item") == 2


# ---------------------------------------------------------------------------
# _group_into_blocks
# ---------------------------------------------------------------------------

class TestGroupIntoBlocks:
    def test_single_block(self):
        spans = [_span(block_index=0), _span(block_index=0, span_index=1)]
        blocks = _group_into_blocks(spans)
        assert len(blocks) == 1
        assert len(blocks[0]) == 2

    def test_two_blocks(self):
        spans = [_span(block_index=0), _span(block_index=1)]
        blocks = _group_into_blocks(spans)
        assert len(blocks) == 2

    def test_blocks_in_document_order(self):
        # Deliberately pass spans out of order — should come out sorted.
        spans = [
            _span("B", block_index=1, page=0),
            _span("A", block_index=0, page=0),
        ]
        blocks = _group_into_blocks(spans)
        assert blocks[0][0].text == "A"
        assert blocks[1][0].text == "B"

    def test_empty_list_returns_empty(self):
        assert _group_into_blocks([]) == []


# ---------------------------------------------------------------------------
# _strip_list_marker
# ---------------------------------------------------------------------------

class TestStripListMarker:
    def test_dash(self):        assert _strip_list_marker("- item") == "item"
    def test_bullet(self):      assert _strip_list_marker("• item") == "item"
    def test_asterisk(self):    assert _strip_list_marker("* item") == "item"
    def test_numbered_dot(self): assert _strip_list_marker("1. item") == "item"
    def test_numbered_paren(self): assert _strip_list_marker("2) item") == "item"
    def test_no_marker(self):   assert _strip_list_marker("plain text") == "plain text"
    def test_leading_whitespace(self): assert _strip_list_marker("  - item") == "item"


# ---------------------------------------------------------------------------
# preamble / postamble
# ---------------------------------------------------------------------------

class TestPreamblePostamble:
    def test_preamble_starts_with_documentclass(self):
        assert preamble().startswith(r"\documentclass{article}")

    def test_preamble_contains_begin_document(self):
        assert r"\begin{document}" in preamble()

    def test_postamble_contains_end_document(self):
        assert r"\end{document}" in postamble()
