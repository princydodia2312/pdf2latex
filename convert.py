"""
convert.py
----------
Entry point for the pdf2TeX command-line tool.

Usage:
    python convert.py input.pdf output.tex
    python convert.py input.pdf output.tex --verbose
"""

from pdf_to_latex.cli import cli

if __name__ == "__main__":
    cli()
