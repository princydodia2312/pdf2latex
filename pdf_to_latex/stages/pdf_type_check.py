"""
stages/pdf_type_check.py
------------------------
Stage 1 of the pdf2TeX pipeline.

Determines whether a PDF is born-digital (has an extractable text layer)
or scanned (image-only, no text layer).

Public API
----------
    run(pdf_path: str) -> Literal["born_digital"]

    Raises ScannedPDFError if the PDF appears to be scanned or has no
    extractable text, so the caller can surface a clear error message
    rather than producing silent empty output.

Design notes
------------
- Heuristic: extract text from the first MIN(3, total_pages) pages.
  If the combined character count (after stripping whitespace) is below
  SCANNED_CHAR_THRESHOLD, treat the document as scanned.
- Mixed PDFs (some pages born-digital, some image-only) are treated as
  born-digital — extraction proceeds on pages that have text; image-only
  pages simply yield no spans. This is acceptable for v0.
- The function never returns "scanned" — it either returns "born_digital"
  or raises. This makes the happy path a plain return value and the error
  path an exception, which is easier to handle in pipeline.py.
"""

from __future__ import annotations

from typing import Literal

import fitz  # PyMuPDF


# Number of pages sampled to decide the document type.
_SAMPLE_PAGES = 3

# If total stripped-character count across sampled pages is below this,
# the PDF is considered scanned / non-extractable.
# Rationale: any real born-digital document page has at least a few dozen
# characters. Near-zero means either a blank doc or a scanned image.
SCANNED_CHAR_THRESHOLD = 50


class ScannedPDFError(Exception):
    """
    Raised when the PDF does not contain an extractable text layer.

    Attributes
    ----------
    pdf_path : str
        Path to the PDF that triggered the error.
    char_count : int
        Number of characters actually extracted from the sampled pages.
    """

    def __init__(self, pdf_path: str, char_count: int) -> None:
        self.pdf_path = pdf_path
        self.char_count = char_count
        super().__init__(
            f"'{pdf_path}' appears to be a scanned or image-only PDF "
            f"(extracted {char_count} characters from the first "
            f"{_SAMPLE_PAGES} page(s), threshold is {SCANNED_CHAR_THRESHOLD}). "
            "Scanned PDF support is planned for v3. "
            "Please provide a born-digital PDF with an extractable text layer."
        )


def run(pdf_path: str) -> Literal["born_digital"]:
    """
    Check whether the PDF at *pdf_path* is born-digital.

    Parameters
    ----------
    pdf_path : str
        Absolute or relative path to the PDF file.

    Returns
    -------
    "born_digital"
        Always returns this string on success, so pipeline.py can assert
        on the return value in tests without importing the literal.

    Raises
    ------
    ScannedPDFError
        If the extracted character count across the first
        MIN(3, n_pages) pages is below SCANNED_CHAR_THRESHOLD.
    FileNotFoundError
        If *pdf_path* does not exist (propagated from PyMuPDF).
    fitz.FileDataError
        If the file is not a valid PDF (propagated from PyMuPDF).
    """
    doc = fitz.open(pdf_path)

    try:
        pages_to_sample = min(_SAMPLE_PAGES, len(doc))
        total_chars = 0

        for page_num in range(pages_to_sample):
            page = doc[page_num]
            text = page.get_text("text")
            # Strip whitespace so blank pages with only newlines don't
            # inflate the count.
            total_chars += len(text.strip())

    finally:
        doc.close()

    if total_chars < SCANNED_CHAR_THRESHOLD:
        raise ScannedPDFError(pdf_path=pdf_path, char_count=total_chars)

    return "born_digital"
