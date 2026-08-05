"""
pipeline.py
-----------
Orchestrator for the pdf2TeX v0 pipeline.

Calls Stages 1–4 in order and returns the final LaTeX source string.
This is the only module that imports from multiple stage modules.
Each stage is called via its run() function; the orchestrator owns
the data flow between them.

Public API
----------
    run(pdf_path: str) -> str
        Full pipeline: PDF → LaTeX source string.

    PipelineError
        Base exception for all recoverable pipeline failures.
        Subclasses carry structured information for clean CLI output.

Stage sequence (v0)
-------------------
    Stage 1: pdf_type_check.run(pdf_path)    → "born_digital" | raises ScannedPDFError
    Stage 2: extraction.run(pdf_path)        → list[SpanRecord]
    Stage 3: labeling.run(spans)             → list[SpanRecord]  (mutates in-place)
    Stage 4: assembly.run(spans)             → str (complete .tex source)

Extension points (v1+)
----------------------
    - Stage 3 (labeling) can be swapped for a classifier with the same signature
    - A Stage 5 (correction) can be inserted between labeling and assembly
    - Template selection can be added between labeling and assembly based on
      spans[0].document_type once the classifier sets it
"""

from __future__ import annotations

from pdf_to_latex.stages import assembly, extraction, labeling
from pdf_to_latex.stages.pdf_type_check import ScannedPDFError
from pdf_to_latex.stages import pdf_type_check


class PipelineError(Exception):
    """
    Base class for all recoverable pipeline errors.
    Carries a user-facing message suitable for CLI output.
    """


class ScannedPDFPipelineError(PipelineError):
    """Raised when Stage 1 detects the PDF has no text layer."""

    def __init__(self, original: ScannedPDFError) -> None:
        self.original = original
        super().__init__(str(original))


class EmptyDocumentError(PipelineError):
    """Raised when extraction succeeds but yields zero spans."""

    def __init__(self, pdf_path: str) -> None:
        self.pdf_path = pdf_path
        super().__init__(
            f"No text could be extracted from '{pdf_path}'. "
            "The PDF may contain only images or have an empty text layer."
        )


def run(pdf_path: str) -> str:
    """
    Run the full pdf2TeX v0 pipeline on *pdf_path*.

    Parameters
    ----------
    pdf_path : str
        Path to the input PDF file.

    Returns
    -------
    str
        Complete LaTeX source, ready to write to a .tex file.

    Raises
    ------
    ScannedPDFPipelineError
        If the PDF appears to be scanned / image-only (Stage 1).
    EmptyDocumentError
        If extraction succeeds but yields no text spans (Stage 2).
    FileNotFoundError
        If *pdf_path* does not exist (propagated from PyMuPDF).
    fitz.FileDataError
        If the file is not a valid PDF (propagated from PyMuPDF).
    """
    # Stage 1 — PDF type check
    try:
        pdf_type_check.run(pdf_path)
    except ScannedPDFError as exc:
        raise ScannedPDFPipelineError(exc) from exc

    # Stage 2 — Extraction
    spans = extraction.run(pdf_path)
    if not spans:
        raise EmptyDocumentError(pdf_path)

    # Stage 3 — Heuristic labeling  (mutates spans in-place, also returns them)
    labeling.run(spans)

    # Stage 4 — LaTeX assembly
    latex_source = assembly.run(spans)

    return latex_source
