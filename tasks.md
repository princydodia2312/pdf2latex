# Tasks — v0 Implementation

Task breakdown for the v0 milestone. Each task maps to a module defined in `requirements.md §6`.
Tasks within a stage can be done in parallel; stages must be done in order.

Status legend: `[ ]` not started · `[x]` done · `[-]` in progress

---

## Stage 0 — Project setup

- [ ] **T0.1** Create project directory structure (`pdf_to_latex/`, `stages/`, `stages/templates/`)
- [ ] **T0.2** Create `schema.py` with the `SpanRecord` dataclass (full schema including v1+ fields with defaults)
- [ ] **T0.3** Create `requirements.txt` with pinned dependencies: `pymupdf`, `click` (for CLI)
- [ ] **T0.4** Create `README.md` with project overview, install instructions, and CLI usage example
- [ ] **T0.5** Initialize git repo, add remote (`https://github.com/princydodia2312/pdf2latex`), push initial commit

---

## Stage 1 — PDF type check (`stages/pdf_type_check.py`)

- [ ] **T1.1** Implement `run(pdf_path: str) -> Literal["born_digital"]` — open file with PyMuPDF
- [ ] **T1.2** Attempt `page.get_text("text")` on first 3 pages; count total characters
- [ ] **T1.3** If character count < 50: raise `ScannedPDFError` with a human-readable message
- [ ] **T1.4** Write unit test: born-digital PDF → returns `"born_digital"`
- [ ] **T1.5** Write unit test: scanned/empty PDF → raises `ScannedPDFError`
- [ ] **T1.6** Commit and push: `git commit -m "stage 1: PDF type check"`

---

## Stage 2 — Extraction (`stages/extraction.py`)

- [ ] **T2.1** Implement `run(pdf_path: str) -> list[SpanRecord]`
- [ ] **T2.2** Traverse `page.get_text("dict")` → blocks → lines → spans; populate text, font_size, color, bbox, page, block_index, line_index, span_index
- [ ] **T2.3** Infer `bold` from font name substrings (`Bold`, `Black`, `Heavy`) and flags bitfield (`flags & 16`)
- [ ] **T2.4** Infer `italic` from font name substrings (`Italic`, `Oblique`) and flags bitfield (`flags & 2`)
- [ ] **T2.5** Extract hyperlinks via `page.get_links()`; match link bbox to span bbox (≥50% overlap); set `link` field
- [ ] **T2.6** Infer alignment per line using 10th/90th percentile margin estimation; assign to all spans in that line
- [ ] **T2.7** Write unit test: verify bold/italic flags are correctly set for a known PDF
- [ ] **T2.8** Write unit test: verify hyperlink URL is correctly associated with the right span
- [ ] **T2.9** Write unit test: verify alignment is correctly inferred for centered and justified lines
- [ ] **T2.10** Commit and push: `git commit -m "stage 2: extraction — text, style, links, alignment"`

---

## Stage 3 — Heuristic labeling (`stages/labeling.py`)

- [ ] **T3.1** Implement `run(spans: list[SpanRecord]) -> list[SpanRecord]`
- [ ] **T3.2** Set `document_type = "unknown"` on all records
- [ ] **T3.3** Compute document-wide median font size
- [ ] **T3.4** Group spans by (page, block_index); compute per-block features: `max_font_size`, `is_bold`, `is_center`, `relative_font_size`
- [ ] **T3.5** Apply label rules in order (heading_1 → heading_2 → heading_3 → list_item → centered_block → body); assign `section_label` and `confidence` to all spans in the block
- [ ] **T3.6** Write unit test: block with relative_font_size ≥ 1.4 and bold → `heading_1`
- [ ] **T3.7** Write unit test: block starting with `•` → `list_item`
- [ ] **T3.8** Write unit test: block with centered alignment → `centered_block`
- [ ] **T3.9** Write unit test: normal body text → `body`
- [ ] **T3.10** Commit and push: `git commit -m "stage 3: heuristic labeling"`

---

## Stage 4 — LaTeX assembly (`stages/assembly.py` + `stages/templates/article.py`)

- [ ] **T4.1** Implement `run(spans: list[SpanRecord]) -> str` in `assembly.py`
- [ ] **T4.2** Implement `escape_latex(text: str) -> str` — escape all special LaTeX characters
- [ ] **T4.3** Implement `format_span(span: SpanRecord) -> str` — apply bold, italic, href wrapping in correct order
- [ ] **T4.4** Implement `article.py` template: emit preamble, dispatch blocks by `section_label`, emit `\end{document}`
- [ ] **T4.5** Handle `list_item` blocks: accumulate consecutive list items into a single `itemize` environment
- [ ] **T4.6** Handle table blocks: emit `% [table omitted — not supported in v0]` comment
- [ ] **T4.7** Write unit test: bold span → `\textbf{...}`
- [ ] **T4.8** Write unit test: italic span → `\textit{...}`
- [ ] **T4.9** Write unit test: linked span → `\href{url}{text}`
- [ ] **T4.10** Write unit test: bold+italic+linked span → `\href{url}{\textbf{\textit{...}}}`
- [ ] **T4.11** Write unit test: special characters in text are escaped before wrapping
- [ ] **T4.12** Write unit test: consecutive list items produce a single `itemize` block
- [ ] **T4.13** Write unit test: complete output starts with `\documentclass{article}` and ends with `\end{document}`
- [ ] **T4.14** Commit and push: `git commit -m "stage 4: LaTeX assembly — article template"`

---

## Stage 5 — Orchestrator + CLI

- [ ] **T5.1** Implement `pipeline.py`: `run(pdf_path: str) -> str` — calls stages 1–4 in order
- [ ] **T5.2** Implement `cli.py`: `python convert.py <input.pdf> <output.tex>` using `click`
- [ ] **T5.3** Handle and surface errors gracefully: `ScannedPDFError`, file-not-found, permission errors
- [ ] **T5.4** Write integration test: run full pipeline on a sample born-digital PDF, verify output compiles with `pdflatex`
- [ ] **T5.5** Commit and push: `git commit -m "stage 5: pipeline orchestrator + CLI"`

---

## Stage 6 — Validation against success criteria

Run all 9 success criteria from `requirements.md §3` and record results below.

- [ ] **V1** Tool runs on 3 different born-digital PDFs without crashing
- [ ] **V2** Output `.tex` compiles with `pdflatex` (zero errors)
- [ ] **V3** Bold spans appear as `\textbf{...}`
- [ ] **V4** Italic spans appear as `\textit{...}`
- [ ] **V5** Hyperlinks appear as `\href{url}{text}` with correct URLs
- [ ] **V6** Large/bold top-of-block text becomes `\section{}` or `\subsection{}`
- [ ] **V7** Centered text renders in `\begin{center}...\end{center}`
- [ ] **V8** Scanned PDF exits with informative error
- [ ] **V9** No text content silently dropped

- [ ] **T6.1** Fix any failures found during validation
- [ ] **T6.2** Final commit and push: `git commit -m "v0: complete — all success criteria passing"`

---

## Dependency map

```
T0 (setup)
  └── T1 (pdf type check)
        └── T2 (extraction)
              └── T3 (labeling)
                    └── T4 (assembly)
                          └── T5 (orchestrator + CLI)
                                └── T6 (validation)
```

T0.2 (`schema.py`) must be complete before any other stage starts — all stages depend on it.
