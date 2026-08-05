"""
pdf_to_latex/cli.py
-------------------
Command-line interface for pdf2TeX.

Invoked via convert.py at the project root. Wraps pipeline.run() with
clean error messages and exit codes so users get actionable feedback
instead of raw tracebacks.

Usage
-----
    python convert.py input.pdf output.tex
    python convert.py input.pdf output.tex --verbose
"""

from __future__ import annotations

import sys

import click

from pdf_to_latex.pipeline import (
    EmptyDocumentError,
    PipelineError,
    ScannedPDFPipelineError,
    run,
)


@click.command()
@click.argument("input_pdf", type=click.Path(exists=True, readable=True, dir_okay=False))
@click.argument("output_tex", type=click.Path(dir_okay=False, writable=True))
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Print progress messages to stderr.")
def cli(input_pdf: str, output_tex: str, verbose: bool) -> None:
    """
    Convert INPUT_PDF to OUTPUT_TEX using style-based heuristics.

    INPUT_PDF must be a born-digital PDF with an extractable text layer.
    OUTPUT_TEX is created or overwritten with the generated LaTeX source.

    Example:

    \b
        python convert.py resume.pdf resume.tex
        pdflatex resume.tex
    """
    if verbose:
        click.echo(f"pdf2TeX v0: converting '{input_pdf}' ...", err=True)

    try:
        if verbose:
            click.echo("  [1/4] Checking PDF type ...", err=True)
        latex_source = run(input_pdf)

    except ScannedPDFPipelineError as exc:
        click.echo(f"\nError: {exc}", err=True)
        click.echo(
            "\nHint: pdf2TeX v0 only supports born-digital PDFs. "
            "Scanned PDF support is planned for v3.",
            err=True,
        )
        sys.exit(1)

    except EmptyDocumentError as exc:
        click.echo(f"\nError: {exc}", err=True)
        sys.exit(1)

    except PipelineError as exc:
        click.echo(f"\nPipeline error: {exc}", err=True)
        sys.exit(1)

    except FileNotFoundError as exc:
        # Should not normally reach here because click.Path(exists=True)
        # validates the input, but handle it defensively.
        click.echo(f"\nError: file not found — {exc}", err=True)
        sys.exit(1)

    except Exception as exc:  # noqa: BLE001
        click.echo(f"\nUnexpected error: {exc}", err=True)
        click.echo(
            "Please report this at https://github.com/princydodia2312/pdf2latex/issues",
            err=True,
        )
        sys.exit(2)

    # Write output
    try:
        with open(output_tex, "w", encoding="utf-8") as f:
            f.write(latex_source)
    except OSError as exc:
        click.echo(f"\nError: could not write output file — {exc}", err=True)
        sys.exit(1)

    if verbose:
        line_count = latex_source.count("\n")
        click.echo(
            f"  Done. Wrote {line_count} lines to '{output_tex}'.",
            err=True,
        )
    else:
        click.echo(f"Done: '{output_tex}'")
