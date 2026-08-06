"""
stages/templates/resume.py
--------------------------
LaTeX resume template for pdf2TeX using the moderncv document class.

Public API
----------
    preamble() -> str
    render_blocks(blocks: list[list[SpanRecord]], format_span_fn) -> str
    postamble() -> str

RESUME_SECTION_KEYWORDS : set[str]
    Lowercase section-header keywords used by the classifier (v1+) to
    recognise resume-specific sections.
"""

from __future__ import annotations

from typing import Callable

from pdf_to_latex.schema import SpanRecord


# ---------------------------------------------------------------------------
# Section keyword vocabulary
# ---------------------------------------------------------------------------

RESUME_SECTION_KEYWORDS: set[str] = {
    "summary",
    "objective",
    "profile",
    "experience",
    "work experience",
    "professional experience",
    "employment",
    "education",
    "academic background",
    "qualifications",
    "skills",
    "technical skills",
    "core competencies",
    "projects",
    "personal projects",
    "academic projects",
    "certifications",
    "certificates",
    "awards",
    "achievements",
    "publications",
    "research",
    "languages",
    "interests",
    "hobbies",
    "references",
    "volunteer",
    "activities",
}


# ---------------------------------------------------------------------------
# Document structure
# ---------------------------------------------------------------------------

def preamble() -> str:
    r"""
    Return the LaTeX document preamble for a moderncv resume.

    Uses:
      - moderncv document class with 'classic' style and 'blue' colour
      - geometry package with scale=0.85
      - inputenc (utf8), fontenc (T1), hyperref
    """
    return r"""\documentclass[11pt,a4paper]{moderncv}
\moderncvstyle{classic}
\moderncvcolor{blue}
\usepackage[scale=0.85]{geometry}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{hyperref}
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
    Render a list of blocks into LaTeX source suitable for a moderncv resume.

    Parameters
    ----------
    blocks : list[list[SpanRecord]]
        Each inner list is one block (all spans share the same page and
        block_index). Blocks are in document order.
    format_span_fn : callable
        Function that takes a SpanRecord and returns a formatted LaTeX
        string (handles bold, italic, href wrapping and escaping).
        Provided by assembly.py.

    Returns
    -------
    str
        LaTeX body source (between preamble and postamble).

    Notes
    -----
    In v0 the document_type is always 'unknown', so this template is not
    yet invoked by the pipeline. It is wired in as a slot for v1 when the
    classifier sets document_type = 'resume' and template selection routes
    here. For now it renders blocks using the same label vocabulary as
    article.py, mapping them to moderncv equivalents where possible.
    """
    from itertools import groupby as _groupby

    lines: list[str] = []
    i = 0

    while i < len(blocks):
        block = blocks[i]
        label = block[0].section_label

        if label == "list_item":
            item_lines, i = _render_itemize_group(blocks, i, format_span_fn)
            lines.extend(item_lines)
        else:
            lines.extend(_render_single_block(block, label, format_span_fn))
            lines.append("")
            i += 1

    return "\n".join(lines)


def _block_content(
    block: list[SpanRecord],
    format_span_fn: Callable[[SpanRecord], str],
) -> str:
    """Concatenate formatted span content for an entire block."""
    from itertools import groupby as _groupby

    line_strings: list[str] = []
    for _key, line_iter in _groupby(
        block, key=lambda s: (s.page, s.block_index, s.line_index)
    ):
        line_spans = list(line_iter)
        line_strings.append("".join(format_span_fn(s) for s in line_spans))
    return " ".join(line_strings)


def _render_single_block(
    block: list[SpanRecord],
    label: str,
    format_span_fn: Callable[[SpanRecord], str],
) -> list[str]:
    """Render one non-list block into moderncv LaTeX lines."""
    content = _block_content(block, format_span_fn)

    # Map generic labels to moderncv equivalents.
    # heading_1 / heading_2 → \section (top-level resume section)
    if label in ("heading_1", "heading_2"):
        return [f"\\section{{{content}}}"]

    # heading_3 → \subsection (sub-section within a resume section)
    if label == "heading_3":
        return [f"\\subsection{{{content}}}"]

    if label == "centered_block":
        return ["\\begin{center}", content, "\\end{center}"]

    if label == "table_omitted":
        return ["% [table omitted --- not supported in v0]"]

    # body → bare paragraph
    return [content]


def _render_itemize_group(
    blocks: list[list[SpanRecord]],
    start: int,
    format_span_fn: Callable[[SpanRecord], str],
) -> tuple[list[str], int]:
    r"""
    Consume consecutive list_item blocks and wrap them in \begin{itemize}.
    Strips the leading list marker from each item's text.
    """
    import re as _re

    _STRIP_RE = _re.compile(
        r"^(\s*([•\-\*·‣◦▪▸►]|(\(?\d+[\.\)])|(\(?[a-zA-Z][\.\)]))\s*)"
    )

    result = ["\\begin{itemize}"]
    i = start

    while i < len(blocks) and blocks[i][0].section_label == "list_item":
        content = _block_content(blocks[i], format_span_fn)
        content = _STRIP_RE.sub("", content, count=1).lstrip()
        result.append(f"  \\item {content}")
        i += 1

    result.append("\\end{itemize}")
    result.append("")
    return result, i
