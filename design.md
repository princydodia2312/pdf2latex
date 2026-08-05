# PDF to LaTeX Converter — Project Design

## 1. Project overview

A tool that converts PDF documents into well-structured, valid LaTeX source files — preserving not just the text content but also the **formatting** (bold, italic, alignment), **hyperlinks**, and **document structure** (headings, sections, lists), which existing online converters typically fail to capture.

### 1.1 Origin problem (why this project exists)

The founder used an existing online PDF-to-LaTeX converter on a resume PDF. The tool successfully extracted the text content, but failed to capture:
- Bold and italic formatting
- Text alignment (centered headers, justified body text)
- Hyperlinks (e.g. GitHub/LinkedIn links) and where they should redirect
- Overall visual/semantic structure

This project exists to solve that specific failure mode, then generalize the solution beyond resumes.

### 1.2 Core insight

This is **not fundamentally an NLP problem** in the classic sense — it is primarily a **PDF parsing and document structure problem**. The reason existing converters fail is that they extract only raw text and discard the rich metadata PDFs actually contain: font name/size/weight, color, position, and separate link-annotation objects.

NLP/ML enters the project specifically at two well-defined points:
1. **Document type classification** (is this a resume / report / plain article / etc.)
2. **Section/line classification** (labeling what role each text block plays, conditioned on document type)

### 1.3 Project goal

Build a **genuinely useful, working tool** (not just a learning exercise) that:
- Accepts a PDF
- Extracts text + full style metadata + links
- Classifies document type and section structure
- Lets the user quickly review/correct only the uncertain parts
- Outputs valid, well-structured LaTeX matching an appropriate template

### 1.4 Generality constraint

The tool must **not** be resume-specific. It must support multiple document types, each routed to its own appropriate template and section vocabulary, with a generic style-based fallback for any unrecognized document type. Resume is the first supported type but the architecture must be type-agnostic from the start.

---

## 2. Scope for v1

**Supported document types (v1):**
1. Resume
2. Report
3. Plain article

**Explicitly deferred to later versions:**
- Math formula recognition (pix2tex / Meta's Nougat)
- Table structure recognition (v1 may preserve tables as images)
- Scanned/image-based PDFs via OCR (v2+)
- Icon font handling (e.g. FontAwesome)
- Multi-format export (Markdown, JSON Resume, HTML)
- ATS-friendliness checker
- Visual diff (render generated LaTeX back to PDF)

---

## 3. Core pipeline architecture

```
PDF input
   │
   ▼
[1] PDF type classification (born-digital vs scanned)
   │
   ▼
[2] Extraction (text + style metadata + links)
   │
   ▼
[3] Document type detection (resume / report / article)
   │
   ▼
[4] Type-conditioned section classification (NLP component)
   │        (falls back to style/position-only heuristics
   │         for unrecognized document types)
   ▼
[5] Template matching (select LaTeX class/structure for detected type)
   │
   ▼
[6] Correction step (human-in-the-loop review of uncertain items only)
   │
   ▼
[7] LaTeX assembly (generate final .tex file)
```

### 3.1 Stage details

**[1] PDF type classification**
Determine whether the PDF is born-digital or scanned. Heuristic: attempt text extraction; if it returns near-nothing, treat as scanned.
- v1: born-digital path only.

**[2] Extraction**
Use PyMuPDF (`fitz`), `page.get_text("dict")` for per-span metadata. Each span carries: font name, flags bitfield (bold/italic), font size, color, and bounding box.
- Hyperlinks: `page.get_links()` returns each link's URL and bounding box. Match against nearby text spans by bbox overlap.
- Alignment: inferred from span x-positions relative to page margins/column width.

**[3] Document type detection**
Classifier (or heuristic in early versions) that determines which supported document type the PDF most resembles.

**[4] Type-conditioned section classification**
Labels each text block with its semantic role using a label set specific to the detected document type:
- Resume → Header/Contact, Experience, Education, Skills, Projects, Summary
- Report/Article → Title, Abstract, Introduction, Body Sections, Headings, References

Implementation options (in increasing sophistication):
- Rule-based keyword matching
- Embeddings + nearest-neighbor
- Fine-tuned small model (e.g. distilbert)
- **Recommended start:** few-shot prompting via Anthropic API

Each classification outputs a **confidence score** to drive the correction UI.

**[5] Fallback path**
For unrecognized document types, fall back to pure style/position-based heuristics (bold + large font → heading; normal weight + indented → body/list).

**[6] Template matching**
- Resume → `moderncv` or `altacv`
- Report / Article → standard `article` class

**[7] Correction step**
Human-in-the-loop: only surface items below a confidence threshold. Confirmed/corrected labels feed into LaTeX generation.

**[8] LaTeX assembly**
- bold → `\textbf{...}`
- italic → `\textit{...}`
- link → `\href{url}{text}`
- centered block → `\begin{center}...\end{center}`
- section label → appropriate environment per template

---

## 4. Intermediate data schema

```python
{
  text: string,
  bold: boolean,
  italic: boolean,
  font_size: number,
  position: { x, y, page },
  link: string | null,
  alignment: "left" | "center" | "right" | "justified",
  document_type: string,          # set at stage 3
  section_label: string,          # set at stage 4
  confidence: number,             # set at stage 4
  user_confirmed: boolean         # set at stage 6 (correction step)
}
```

---

## 5. User-facing flow (UI/UX)

### 5.1 Three-step flow

```
1. Upload  →  2. Review  →  3. Download .tex
```

**Step 1 — Upload**
Drag-and-drop or file browser. After upload, stages 1–5 run automatically in the background.

**Step 2 — Review**
- Render the document as a live preview
- Only highlight words/lines the classifier is uncertain about
- Clicking a highlighted item opens a small inline popover
- Summary: "2 things need a quick check"
- If nothing needs review: "Looks good, generate LaTeX"
- Document type shown as a badge with a manual override option
- Template selector available near the generate action

**Step 3 — Download**
Final `.tex` file output.

### 5.2 What is/isn't visible to the user

**Always backend / invisible:**
- Classifiers running
- Raw confidence scores as numbers
- Which method produced a label

**Surfaced to the user:**
- Document type badge (with override)
- Only low-confidence decisions (as inline highlights + correction popovers)

---

## 6. Improving classification accuracy

1. **Rich input features** — feed classifier text + style/position metadata, not text alone
2. **Few-shot LLM classification** — prototype with Anthropic API before investing in training
3. **Feedback/active learning loop** — log user corrections to improve prompts or retrain models
4. **Hybrid rules + ML** — use rules for obvious cases, ML for ambiguous ones
5. **Confidence calibration** — verify stated confidence against real-world accuracy on held-out set
6. **Proper evaluation setup** — maintain held-out test set; track per-class precision/recall
7. **Data augmentation** — vary section ordering, formatting, header phrasing for robustness

---

## 7. Future add-ons (post-v1)

- **Template intelligence** — detect which template family a document resembles
- **Correction loop** — human-in-the-loop review (see §5.2)
- **Multi-format export** — Markdown, JSON Resume, HTML
- **ATS-friendliness checker** — flag content inside image/text-box
- **Visual diff** — render generated LaTeX to PDF, show side-by-side comparison
- **Icon/font fallback** — detect icon fonts, map to `\faIcon{}` or plain text

---

## 8. Suggested build order

1. **v0** — Born-digital PDFs → LaTeX with heading/paragraph structure only. No math, no tables, no classifier (style-only fallback). Prove the end-to-end pipeline works.
2. **v1** — Add document type detection + section classification (few-shot LLM approach) for resume / report / article. Add template matching. Add correction-loop UI.
3. **v2** — Add math formula recognition via pix2tex or Nougat.
4. **v3** — Add scanned PDF support via OCR branch.
5. **v4** — Tackle tables and figures properly.

---

## 9. Tech stack

- **Language:** Python
- **PDF parsing:** PyMuPDF (fitz)
- **Classification:** few-shot prompting via Anthropic API → embeddings/nearest-neighbor or fine-tuned distilbert as upgrade path
- **Math (v2+):** pix2tex (LaTeX-OCR) or Meta's Nougat
- **OCR (v3+):** Tesseract or docTR
- **LaTeX templates:** `moderncv` / `altacv` for resumes, `article` class for reports/articles

---

## 10. Open decisions

- Exact confidence threshold for "needs review" vs "trusted silently" — needs tuning once classifier exists
- Whether icon fonts get mapped to LaTeX icon packages or stripped to text (deferred)
- Whether v1 correction loop is web-based or another interface — interaction pattern is decided (preview + inline highlight + popover), framework is not
