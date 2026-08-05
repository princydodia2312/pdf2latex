r"""
stages/assembly.py
------------------
Stage 4 of the pdf2TeX pipeline.

Translates a list of labeled SpanRecords into a complete, compilable
LaTeX source string.

Responsibilities
----------------
  1. escape_latex()   -- escape the 10 LaTeX special characters in raw text
  2. format_span()    -- wrap escaped text with \textbf, \textit, \href
                        in the correct nesting order
  3. run()            -- group spans into blocks, select a template, and
                        delegate block-level rendering to the template

Public API
----------
    run(spans: list[SpanRecord]) -> str
    escape_latex(text: str) -> str          (exposed for testing)
    format_span(span: SpanRecord) -> str    (exposed for testing)

Inline formatting rules (applied in this order)
------------------------------------------------
  1. escape_latex(text)           -- always first
  2. wrap \textit{...}            -- if italic
  3. wrap \textbf{...}            -- if bold  (wraps around \textit if both)
  4. wrap \href{url}{...}         -- if link  (outermost wrapper)

So bold+italic+link becomes: \href{url}{\textbf{\textit{text}}}

Special LaTeX characters escaped
---------------------------------
  {  ->  \{                    (must come before backslash)
  }  ->  \}                    (must come before backslash)
  \  ->  \textbackslash{}
  &  ->  \&
  %  ->  \%
  $  ->  \$
  #  ->  \#
  _  ->  \_
  ~  ->  \textasciitilde{}
  ^  ->  \textasciicircum{}

Note: braces are escaped first so the braces inside \textbackslash{}
are never re-escaped. This avoids producing \textbackslash\{\}.
"""

from __future__ import annotations

from itertools import groupby

from pdf_to_latex.schema import SpanRecord
from pdf_to_latex.stages.templates import article as _article_template

# ---------------------------------------------------------------------------
# Special-character escaping
# ---------------------------------------------------------------------------

# Single-pass escape using re.sub with a dispatch dict.
# All 10 special characters are matched in one regex pass, so no
# replacement can ever be re-processed by a subsequent rule.
import re as _re

_LATEX_SPECIAL_RE = _re.compile(r'[\\&%$#_{}~^]')

_LATEX_ESCAPE_MAP: dict[str, str] = {
    "\\": r"\textbackslash{}",
    "&":  r"\&",
    "%":  r"\%",
    "$":  r"\$",
    "#":  r"\#",
    "_":  r"\_",
    "{":  r"\{",
    "}":  r"\}",
    "~":  r"\textasciitilde{}",
    "^":  r"\textasciicircum{}",
}


def escape_latex(text: str) -> str:
    """
    Escape all LaTeX special characters in *text*.

    Uses a single regex pass so no replacement string is ever re-processed
    by a subsequent rule. This correctly handles inputs like a lone backslash
    (produces r'\\textbackslash{}') and lone braces (produces r'\\{' / r'\\}')
    without interference.

    Must be called before any LaTeX command wrappers are applied.
    """
    return _LATEX_SPECIAL_RE.sub(lambda m: _LATEX_ESCAPE_MAP[m.group()], text)


# ---------------------------------------------------------------------------
# Inline span formatting
# ---------------------------------------------------------------------------

def format_span(span: SpanRecord) -> str:
    r"""
    Return the LaTeX representation of a single span's inline content.

    Applies escape_latex first, then wraps with formatting commands in the
    order: italic -> bold -> href (innermost to outermost).

    An empty or whitespace-only span returns an empty string.
    An empty or whitespace-only span returns an empty string.
    """
    text = span.text
    if not text.strip():
        return ""

    # Step 1 — escape special characters
    result = escape_latex(text)

    # Step 2 — italic (innermost)
    if span.italic:
        result = f"\\textit{{{result}}}"

    # Step 3 — bold (wraps italic if both)
    if span.bold:
        result = f"\\textbf{{{result}}}"

    # Step 4 — hyperlink (outermost)
    if span.link:
        # Escape the URL itself (% is the only realistic special char in URLs
        # that LaTeX cares about; others are handled by the hyperref package).
        safe_url = span.link.replace("%", r"\%")
        result = f"\\href{{{safe_url}}}{{{result}}}"

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(spans: list[SpanRecord]) -> str:
    """
    Assemble a complete LaTeX document from labeled SpanRecords.

    Parameters
    ----------
    spans : list[SpanRecord]
        Output from Stage 3 (labeling). Each span must have section_label,
        bold, italic, link, and text populated.

    Returns
    -------
    str
        A complete LaTeX source string, ready to write to a .tex file and
        compile with pdflatex.
    """
    # Group spans into blocks. Each block is a list of spans sharing the
    # same (page, block_index). Blocks are produced in document order.
    blocks = _group_into_blocks(spans)

    # Select template (always article in v0).
    template = _article_template

    # Assemble.
    parts: list[str] = [
        template.preamble(),
        template.render_blocks(blocks, format_span),
        template.postamble(),
    ]
    return "".join(parts)


# ---------------------------------------------------------------------------
# Block grouping
# ---------------------------------------------------------------------------

def _group_into_blocks(spans: list[SpanRecord]) -> list[list[SpanRecord]]:
    """
    Group spans by (page, block_index) in document order.

    Returns a list of blocks; each block is a non-empty list of SpanRecords
    sorted by (line_index, span_index).
    """
    # Sort to guarantee document order before grouping.
    sorted_spans = sorted(
        spans,
        key=lambda s: (s.page, s.block_index, s.line_index, s.span_index),
    )

    blocks: list[list[SpanRecord]] = []
    for _key, group in groupby(
        sorted_spans, key=lambda s: (s.page, s.block_index)
    ):
        block = list(group)
        if block:
            blocks.append(block)

    return blocks
