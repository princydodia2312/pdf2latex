r"""
stages/templates/article.py
----------------------------
LaTeX article-class template for pdf2TeX v0.

Responsible for:
  - Emitting the document preamble and \end{document}
  - Translating each section_label into the appropriate LaTeX environment
    or command
  - Merging consecutive list_item blocks into a single itemize environment

This module is intentionally kept separate from assembly.py so that
adding a new template in v1 (e.g. moderncv.py) means adding a new file
here, not touching the assembly orchestrator.

Public API
----------
    preamble() -> str
    render_blocks(blocks: list[list[SpanRecord]], format_span_fn) -> str
    postamble() -> str

The template receives pre-formatted span strings from assembly.py via the
format_span_fn callback -- it does not do inline formatting itself.
"""

from __future__ import annotations

from typing import Callable

from pdf_to_latex.schema import SpanRecord


# ---------------------------------------------------------------------------
# Document structure
# ---------------------------------------------------------------------------

def preamble() -> str:
    """Return the LaTeX document preamble for the article class."""
    return r"""\documentclass{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{hyperref}
\usepackage{parskip}
\begin{document}
"""


def postamble() -> str:
    """Return the LaTeX document closing."""
    return r"\end{document}" + "\n"


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------

def render_blocks(
    blocks: list[list[SpanRecord]],
    format_span_fn: Callable[[SpanRecord], str],
) -> str:
    """
    Render a list of blocks into LaTeX source.

    Parameters
    ----------
    blocks : list[list[SpanRecord]]
        Each inner list is one block (all spans share the same page and
        block_index). Blocks are in document order.
    format_span_fn : callable
        A function that takes a SpanRecord and returns a LaTeX string for
        its inline content (handles bold, italic, href wrapping and
        special-character escaping). Provided by assembly.py.

    Returns
    -------
    str
        LaTeX source for the body of the document (between preamble and
        postamble), with a trailing newline.
    """
    lines: list[str] = []
    i = 0

    while i < len(blocks):
        block = blocks[i]
        label = block[0].section_label  # all spans in a block share the label

        if label == "list_item":
            # Accumulate consecutive list_item blocks into one environment.
            item_lines, i = _render_itemize_group(blocks, i, format_span_fn)
            lines.extend(item_lines)
        else:
            lines.extend(_render_single_block(block, label, format_span_fn))
            lines.append("")   # blank line between blocks
            i += 1

    return "\n".join(lines)


def _render_single_block(
    block: list[SpanRecord],
    label: str,
    format_span_fn: Callable[[SpanRecord], str],
) -> list[str]:
    """
    Render one non-list block into a list of LaTeX lines.
    """
    content = _block_content(block, format_span_fn)

    if label == "heading_1":
        return [f"\\section{{{content}}}"]

    if label == "heading_2":
        return [f"\\subsection{{{content}}}"]

    if label == "heading_3":
        return [f"\\subsubsection{{{content}}}"]

    if label == "centered_block":
        return ["\\begin{center}", content, "\\end{center}"]

    if label == "table_omitted":
        return ["% [table omitted --- not supported in v0]"]

    # body (and any unrecognised label) → bare paragraph
    return [content]


def _render_itemize_group(
    blocks: list[list[SpanRecord]],
    start: int,
    format_span_fn: Callable[[SpanRecord], str],
) -> tuple[list[str], int]:
    r"""
    Consume consecutive list_item blocks starting at *start* and return
    a (lines, next_index) tuple.

    Strips the leading list marker from each block's text so LaTeX renders
    it cleanly with \item instead of double-marking it.
    """
    result = ["\\begin{itemize}"]
    i = start

    while i < len(blocks) and blocks[i][0].section_label == "list_item":
        block = blocks[i]
        content = _block_content(block, format_span_fn)
        # Strip the leading marker character(s) so \item doesn't double-bullet.
        content = _strip_list_marker(content)
        result.append(f"  \\item {content}")
        i += 1

    result.append("\\end{itemize}")
    result.append("")   # blank line after environment
    return result, i


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _block_content(
    block: list[SpanRecord],
    format_span_fn: Callable[[SpanRecord], str],
) -> str:
    """
    Concatenate the formatted content of all spans in a block into a
    single string, joining spans on the same line with a space where needed
    and separating lines with a single newline.

    Within a line, spans are concatenated directly (no extra space) because
    PyMuPDF already preserves inter-word spacing inside the text field.
    Between lines within the same block, a space is inserted to avoid
    words from different lines running together.
    """
    # Group spans by line_index to preserve line breaks within a block.
    from itertools import groupby
    line_strings: list[str] = []

    for _line_key, line_iter in groupby(block, key=lambda s: (s.page, s.block_index, s.line_index)):
        line_spans = list(line_iter)
        line_strings.append("".join(format_span_fn(s) for s in line_spans))

    # Join lines with a space so adjacent lines form readable sentences.
    return " ".join(line_strings)


# Matches a leading list marker and optional whitespace.
import re as _re
_STRIP_MARKER_RE = _re.compile(
    r"^(\s*"
    r"([•\-\*·‣◦▪▸►]"
    r"|(\(?\d+[\.\)])"
    r"|(\(?[a-zA-Z][\.\)])"
    r")\s*)"
)


def _strip_list_marker(text: str) -> str:
    """Remove a leading list marker from *text*, if present."""
    return _STRIP_MARKER_RE.sub("", text, count=1).lstrip()
