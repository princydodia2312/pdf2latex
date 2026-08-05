# pdf2TeX

Convert born-digital PDFs into well-structured, valid LaTeX — preserving bold, italic, alignment, hyperlinks, and document structure. Not just raw text.

## Why

Existing PDF-to-LaTeX converters extract plain text and throw away everything else: font weight, font size, text alignment, and hyperlink targets. This tool reads the full style metadata that PDFs actually contain and uses it to produce LaTeX that looks like the original document.

## Status

**v0 — in progress.** Born-digital PDFs → LaTeX with heading/paragraph structure, bold/italic formatting, and hyperlinks. Style-only heuristics, no ML classifier yet.

See [`design.md`](design.md) for the full project spec and [`requirements.md`](requirements.md) for v0 scope and success criteria.

## Supported document types

| Version | Types |
|---------|-------|
| v0 | Any born-digital PDF (generic `article` output) |
| v1 | Resume, Report, Plain article (type-specific templates) |

## Requirements

- Python 3.11+
- A LaTeX distribution (e.g. [TeX Live](https://tug.org/texlive/) or [MiKTeX](https://miktex.org/)) to compile the output

## Install

```bash
git clone https://github.com/princydodia2312/pdf2latex.git
cd pdf2latex
pip install -r requirements.txt
```

## Usage

```bash
python convert.py input.pdf output.tex
```

Then compile the output:

```bash
pdflatex output.tex
```

## Project structure

```
pdf_to_latex/
├── pipeline.py              # orchestrator — calls stages in order
├── schema.py                # SpanRecord dataclass — shared data contract
├── stages/
│   ├── pdf_type_check.py    # Stage 1: born-digital vs scanned detection
│   ├── extraction.py        # Stage 2: text + style + links via PyMuPDF
│   ├── labeling.py          # Stage 3: heuristic section labeling
│   ├── assembly.py          # Stage 4: LaTeX generation
│   └── templates/
│       └── article.py       # article class template
└── cli.py                   # CLI entry point
tests/
design.md                    # full project specification
requirements.md              # v0 feature spec and success criteria
tasks.md                     # v0 implementation task list
```

## Pipeline (v0)

```
PDF input
  │
  ▼
[1] PDF type check        — abort if scanned (no text layer)
  │
  ▼
[2] Extraction            — PyMuPDF: text + bold/italic/size + links + alignment
  │
  ▼
[3] Heuristic labeling    — heading_1/2/3, list_item, centered_block, body
  │
  ▼
[4] LaTeX assembly        — article class, \textbf, \textit, \href, \section
  │
  ▼
output.tex
```

## What v0 preserves

| Source feature | LaTeX output |
|---|---|
| Bold text | `\textbf{...}` |
| Italic text | `\textit{...}` |
| Bold + italic | `\textbf{\textit{...}}` |
| Hyperlink | `\href{url}{text}` |
| Centered block | `\begin{center}...\end{center}` |
| Large/bold heading | `\section{}` / `\subsection{}` |
| List items | `\begin{itemize}...\item...\end{itemize}` |
| Body text | bare paragraph |

## What v0 does not handle

- Scanned / image-based PDFs (v3+)
- Math formulas (v2+)
- Tables (v4+)
- Document type detection and type-specific templates (v1+)
- Human-in-the-loop correction UI (v1+)

## Running tests

```bash
pytest tests/
```
