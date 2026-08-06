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
# Internal helpers
# ---------------------------------------------------------------------------

import re as _re

# Strips a leading bullet/numbered-list marker and surrounding whitespace.
_STRIP_MARKER_RE = _re.compile(
    r"^(\s*([•\-\*·‣◦▪▸►]|(\(?\d+[\.\)])|(\(?[a-zA-Z][\.\)]))\s*)"
)


def _block_content(
    block: list[SpanRecord],
    format_span_fn: Callable[[SpanRecord], str],
) -> str:
    """
    Concatenate the formatted content of all spans in *block* into one string.
    Spans on the same line are concatenated directly; adjacent lines are joined
    with a space so words don't run together.
    """
    from itertools import groupby as _groupby

    line_strings: list[str] = []
    for _key, line_iter in _groupby(
        block, key=lambda s: (s.page, s.block_index, s.line_index)
    ):
        line_strings.append("".join(format_span_fn(s) for s in line_iter))
    return " ".join(line_strings)


def _raw_text(block: list[SpanRecord]) -> str:
    """Return the plain (un-formatted) concatenated text of all spans in *block*."""
    return " ".join(s.text for s in block).strip()


def _is_person_name(text: str) -> bool:
    """
    Return True if *text* looks like a person's name:
      - 1 to 5 words
      - no digit characters
      - lowercased form is NOT a known section keyword
    """
    words = text.split()
    if not (1 <= len(words) <= 5):
        return False
    if any(ch.isdigit() for ch in text):
        return False
    if text.strip().lower() in RESUME_SECTION_KEYWORDS:
        return False
    return True


def _is_section_keyword(text: str) -> bool:
    """Return True if the block's lowercased plain text matches a section keyword."""
    return text.strip().lower() in RESUME_SECTION_KEYWORDS


def _split_name(text: str) -> tuple[str, str]:
    """
    Split *text* into (firstname, lastname).
    Everything up to the last word is the first name; the last word is the last name.
    Single-word names use the word as firstname and an empty string as lastname.
    """
    words = text.split()
    if len(words) == 1:
        return words[0], ""
    return " ".join(words[:-1]), words[-1]


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------

def render_blocks(
    blocks: list[list[SpanRecord]],
    format_span_fn: Callable[[SpanRecord], str],
) -> str:
    r"""
    Render a list of blocks into LaTeX source suitable for a moderncv resume.

    Rules (applied in order per block)
    ------------------------------------
    1. The very first heading_1 block that looks like a person name
       (1–5 words, no digits, not a section keyword) becomes
       ``\name{firstname}{lastname}``.

    2. Any centered_block or body block appearing within the first 3
       blocks after the name block becomes ``\address{content}{}{}``.

    3. Any block whose lowercased plain text matches a word in
       RESUME_SECTION_KEYWORDS becomes ``\section{content}``.

    4. Any other heading_1 or heading_2 block becomes
       ``\subsection{content}``.

    5. Consecutive list_item blocks are wrapped in a single
       ``\begin{itemize}...\end{itemize}`` with ``\item`` for each,
       stripping the leading bullet character.

    6. centered_block (not caught by rule 2) becomes
       ``\begin{center}...\end{center}``.

    7. body (not caught by rule 2) renders as a bare paragraph.

    Parameters
    ----------
    blocks : list[list[SpanRecord]]
        Each inner list is one block in document order.
    format_span_fn : callable
        Provided by assembly.py — formats a single SpanRecord into LaTeX.

    Returns
    -------
    str
        LaTeX body source (to be placed between preamble and postamble).
    """
    lines: list[str] = []

    # Track whether we have already emitted the \name command.
    name_emitted = False
    # Index of the name block so we can count the 3 blocks after it.
    name_block_idx: int = -1

    i = 0
    while i < len(blocks):
        block  = blocks[i]
        label  = block[0].section_label
        raw    = _raw_text(block)
        content = _block_content(block, format_span_fn)

        # ------------------------------------------------------------------
        # Rule 5 — consecutive list_item blocks → single itemize environment
        # ------------------------------------------------------------------
        if label == "list_item":
            item_lines, i = _render_itemize_group(blocks, i, format_span_fn)
            lines.extend(item_lines)
            continue

        # ------------------------------------------------------------------
        # Rule 1 — first heading_1 that looks like a person name → \name
        # ------------------------------------------------------------------
        if label == "heading_1" and not name_emitted and _is_person_name(raw):
            firstname, lastname = _split_name(raw)
            lines.append(f"\\name{{{firstname}}}{{{lastname}}}")
            lines.append("")
            name_emitted = True
            name_block_idx = i
            i += 1
            continue

        # ------------------------------------------------------------------
        # Rule 2 — centered_block or body within 3 blocks after the name → \address
        # ------------------------------------------------------------------
        if (
            name_emitted
            and name_block_idx >= 0
            and (i - name_block_idx) <= 3
            and label in ("centered_block", "body")
        ):
            lines.append(f"\\address{{{content}}}{{}}{{}}")
            lines.append("")
            i += 1
            continue

        # ------------------------------------------------------------------
        # Rule 3 — block text matches a section keyword → \section
        # ------------------------------------------------------------------
        if _is_section_keyword(raw):
            lines.append(f"\\section{{{content}}}")
            lines.append("")
            i += 1
            continue

        # ------------------------------------------------------------------
        # Rule 4 — remaining heading_1 / heading_2 → \subsection
        # ------------------------------------------------------------------
        if label in ("heading_1", "heading_2"):
            lines.append(f"\\subsection{{{content}}}")
            lines.append("")
            i += 1
            continue

        # heading_3 → \subsection as well (finer sub-heading in a resume)
        if label == "heading_3":
            lines.append(f"\\subsection{{{content}}}")
            lines.append("")
            i += 1
            continue

        # ------------------------------------------------------------------
        # Rule 6 — centered_block (not address) → center environment
        # ------------------------------------------------------------------
        if label == "centered_block":
            lines.extend(["\\begin{center}", content, "\\end{center}", ""])
            i += 1
            continue

        # Table omitted
        if label == "table_omitted":
            lines.append("% [table omitted --- not supported in v0]")
            lines.append("")
            i += 1
            continue

        # ------------------------------------------------------------------
        # Rule 7 — body → bare paragraph
        # ------------------------------------------------------------------
        lines.append(content)
        lines.append("")
        i += 1

    return "\n".join(lines)


def _render_itemize_group(
    blocks: list[list[SpanRecord]],
    start: int,
    format_span_fn: Callable[[SpanRecord], str],
) -> tuple[list[str], int]:
    r"""
    Consume consecutive list_item blocks starting at *start*.
    Returns (latex_lines, next_block_index).
    Strips the leading bullet/number marker from each item.
    """
    result = ["\\begin{itemize}"]
    i = start

    while i < len(blocks) and blocks[i][0].section_label == "list_item":
        content = _block_content(blocks[i], format_span_fn)
        content = _STRIP_MARKER_RE.sub("", content, count=1).lstrip()
        result.append(f"  \\item {content}")
        i += 1

    result.append("\\end{itemize}")
    result.append("")
    return result, i
