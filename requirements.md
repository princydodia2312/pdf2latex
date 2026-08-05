# Requirements — v0 Milestone

## 1. Goal

Prove the end-to-end pipeline works: a born-digital PDF goes in, a valid and structurally faithful `.tex` file comes out — preserving bold, italic, font-size hierarchy, text alignment, and hyperlinks, using nothing but style/position heuristics (no classifier, no ML, no human review step).

The output must be **valid, compilable LaTeX** that a human can clean up in minutes — not hours.

---

## 2. Scope

### In scope

- Born-digital PDFs only (has an extractable text layer)
- Text extraction with per-span style metadata: font name, font size, bold flag, italic flag, bounding box, color
- Hyperlink extraction and association with text spans
- Text alignment inference from bounding box positions
- Style-only heuristic labeling: heading vs. body vs. list item vs. centered block
- LaTeX assembly using the standard `article` class for all document types
- Single `.tex` file output
- CLI invocation: `python convert.py input.pdf output.tex`

### Out of scope for v0

- Document type detection (resume vs. report vs. article) — architecture leaves a slot; heuristics fill it with `"unknown"`
- Section classification using NLP or ML
- Human-in-the-loop correction step
- Math formula recognition
- Table structure recognition — tables are skipped with an emitted LaTeX comment, not silently dropped
- Scanned/image-based PDFs — tool exits with a clear error if text extraction returns nothing
- Icon font handling
- Multi-page layout reconstruction (e.g. two-column text reflow)
- Any web UI

---

## 3. Success criteria

Pass all of these with a representative sample PDF for each case.

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | Tool runs to completion on a born-digital PDF without crashing | Run CLI on 3 different PDFs; exit code 0 each time |
| 2 | Output `.tex` compiles without errors | Run `pdflatex output.tex`; zero errors in log |
| 3 | Bold text in source appears as `\textbf{...}` in output | Manual inspection on a PDF with known bold spans |
| 4 | Italic text in source appears as `\textit{...}` in output | Manual inspection on a PDF with known italic spans |
| 5 | Hyperlinks appear as `\href{url}{text}` with correct URLs | Manual inspection; compare link URLs to source PDF |
| 6 | Large/bold top-of-block text is marked as a heading | Check that such spans become `\section{}` or `\subsection{}` in output |
| 7 | Centered text renders inside `\begin{center}...\end{center}` | Manual inspection on a PDF with centered lines |
| 8 | Scanned PDF produces an informative error, not a crash or silent empty output | Run on a known scanned PDF; verify error message |
| 9 | No text content is silently dropped — every extractable span appears somewhere in the output | Diff plain-text extraction against plain-text dump of the `.tex` file |

---

## 4. Pipeline (v0)

Four stages, each an independent module with a typed input and output. Stages do not call each other — composed by a thin orchestrator (`pipeline.py`).

```
[input.pdf]
     │
     ▼
Stage 1: PDF Type Check
     │  input:  file path
     │  output: PDFType ("born_digital" | exits with error if scanned)
     ▼
Stage 2: Extraction
     │  input:  file path
     │  output: List[SpanRecord]
     ▼
Stage 3: Heuristic Labeling
     │  input:  List[SpanRecord]
     │  output: List[SpanRecord]  (section_label, document_type,
     │                             confidence fields populated)
     ▼
Stage 4: LaTeX Assembly
     │  input:  List[SpanRecord]
     │  output: string (complete .tex source)
     ▼
[output.tex]
```

### Stage 1 — PDF type check

- Use PyMuPDF; call `page.get_text("text")` on first 3 pages
- If total character count < 50 across 3 pages → classify as scanned, exit with error
- Mixed PDFs (partially born-digital): proceed on pages that have text; image-only pages yield no spans

### Stage 2 — Extraction

Library: `pymupdf` (import as `fitz`)

- `page.get_text("dict")` → blocks → lines → spans
- Per span: `text`, `bold` (font name + flags bitfield), `italic` (font name + flags), `font_size`, `color`, `bbox`
- Hyperlinks: `page.get_links()` → match link bbox against span bboxes (≥50% overlap → span is linked)
- Alignment: computed per line from x0/x1 vs. page margins (estimated as 10th/90th percentile x0/x1 across all lines on that page)
  - x0 near left margin AND x1 near right margin → `"justified"`
  - x0 far from left, centered on page → `"center"`
  - x1 near right, x0 far from left → `"right"`
  - otherwise → `"left"`

### Stage 3 — Heuristic labeling

- `document_type` = `"unknown"` for all records in v0
- Labels assigned at block granularity (all spans in a block share the same label)
- Per-block features: `max_font_size`, `is_bold`, `is_center`, `relative_font_size` (= max_font_size / median_font_size_of_document)

Label rules (first match wins):

| Condition | Label | Confidence |
|-----------|-------|------------|
| `relative_font_size ≥ 1.4` AND `is_bold` | `"heading_1"` | 0.85 |
| `relative_font_size ≥ 1.2` AND `is_bold` | `"heading_2"` | 0.80 |
| `relative_font_size ≥ 1.1` OR `is_bold` | `"heading_3"` | 0.70 |
| Text starts with `-`, `•`, `*`, or digit+`.` | `"list_item"` | 0.90 |
| `is_center` | `"centered_block"` | 0.75 |
| fallthrough | `"body"` | 0.95 |

Confidence values are static placeholders in v0 — replaced by real classifier scores in v1.

### Stage 4 — LaTeX assembly

**Preamble (always emitted):**
```latex
\documentclass{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{hyperref}
\usepackage{parskip}
\begin{document}
```

**Block emission by label:**

| Label | LaTeX output |
|-------|-------------|
| `heading_1` | `\section{...}` |
| `heading_2` | `\subsection{...}` |
| `heading_3` | `\subsubsection{...}` |
| `centered_block` | `\begin{center}...\end{center}` |
| `list_item` | Consecutive items merged into `\begin{itemize}...\item...\end{itemize}` |
| `body` | Bare paragraph text, separated by blank lines |

**Inline span formatting:**
- `bold` → `\textbf{...}`
- `italic` → `\textit{...}`
- `bold AND italic` → `\textbf{\textit{...}}`
- `link ≠ null` → `\href{url}{text}` (applied after bold/italic wrapping)
- Special LaTeX characters (`& % $ # _ { } ~ ^ \`) must be escaped before wrapping

**Tables:** emit `% [table omitted — not supported in v0]` comment; never silently drop content.

---

## 5. Intermediate data schema

```python
@dataclass
class SpanRecord:
    # Set by Stage 2: Extraction
    text: str
    bold: bool
    italic: bool
    font_size: float
    color: int                               # RGB as integer
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    page: int                                # 0-indexed
    block_index: int
    line_index: int
    span_index: int
    link: str | None
    alignment: Literal["left", "center", "right", "justified"]

    # Set by Stage 3: Labeling (heuristic in v0, classifier in v1+)
    document_type: str    # "unknown" in v0
    section_label: str    # "heading_1" / "heading_2" / "body" / "list_item" / etc.
    confidence: float     # static placeholder in v0

    # Set by Stage 6: Correction (not present in v0, defaults to False)
    user_confirmed: bool = False
```

---

## 6. Module structure

```
pdf_to_latex/
├── pipeline.py              # orchestrator: calls stages in order, owns I/O
├── stages/
│   ├── pdf_type_check.py    # Stage 1
│   ├── extraction.py        # Stage 2
│   ├── labeling.py          # Stage 3 — heuristics in v0, swapped for classifier in v1
│   ├── assembly.py          # Stage 4
│   └── templates/
│       └── article.py       # article class template logic
├── schema.py                # SpanRecord dataclass
└── cli.py                   # entry point: parse args, call pipeline.py
```

**Constraints:**
- `pipeline.py` is the only file that imports from multiple stages
- Each stage exposes exactly one public function: `def run(input) -> output`
- `schema.py` has no imports from other project modules
- Adding a new template in v1 = adding a new file, not modifying `assembly.py`

---

## 7. Extension points for v1+

| v1 feature | How it plugs in |
|---|---|
| Document type classifier | Replace `labeling.py`'s `run()` — same function signature |
| Section classifier | Same, or split into `type_detection.py` + `section_classification.py` |
| Correction UI | New Stage 5 inserted between `labeling.py` and `assembly.py` in `pipeline.py` |
| Resume template | Add `stages/templates/moderncv.py`; template selection in `pipeline.py` |
| Math recognition | Pre-pass before assembly; image blocks → pix2tex → `SpanRecord` with `section_label = "math"` |

---

## 8. Open decisions (v0 does not resolve)

- Confidence threshold for the correction UI
- LLM prompt design for section classification
- Template selection UX
- Multi-column layout handling
- Icon font handling
