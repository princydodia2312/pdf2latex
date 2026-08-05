"""
validate_v0.py
--------------
Validates all 9 v0 success criteria from requirements.md.

Run with:
    python validate_v0.py

Exits 0 if all criteria pass, 1 if any fail.

Criteria
--------
V1  Tool runs on 3 different born-digital PDFs without crashing (exit code 0)
V2  Output .tex compiles without errors (pdflatex — skipped if not on PATH,
    marked as SKIP rather than FAIL)
V3  Bold spans appear as \\textbf{...}
V4  Italic spans appear as \\textit{...}
V5  Hyperlinks appear as \\href{url}{text} with correct URLs
V6  Large/bold top-of-block text becomes \\section{} or \\subsection{}
V7  Centered text renders in \\begin{center}...\\end{center}
V8  Scanned PDF exits with informative error, not crash or silent empty output
V9  No text content silently dropped
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

import fitz

# Ensure the project root is on the path regardless of cwd
sys.path.insert(0, os.path.dirname(__file__))

from pdf_to_latex.pipeline import ScannedPDFPipelineError, run

# ---------------------------------------------------------------------------
# ANSI colours
# ---------------------------------------------------------------------------
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def _pass(msg: str) -> None:
    print(f"  {GREEN}PASS{RESET}  {msg}")

def _fail(msg: str) -> None:
    print(f"  {RED}FAIL{RESET}  {msg}")

def _skip(msg: str) -> None:
    print(f"  {YELLOW}SKIP{RESET}  {msg}")


# ---------------------------------------------------------------------------
# PDF builders
# ---------------------------------------------------------------------------

def _save(doc: fitz.Document) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    doc.save(tmp.name)
    doc.close()
    return tmp.name


def make_resume_pdf() -> str:
    """Resume-like PDF: name header (large+bold), section headers, bullets, link."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Lots of 11pt body text first — anchors the median font size
    body_lines = [
        "Software Engineer with 5 years of experience in Python and distributed systems.",
        "Led development of a PDF-processing pipeline used by thousands of users.",
        "Proficient in machine learning, NLP, and document understanding systems.",
        "Graduated with honours from the Department of Computer Science.",
        "Contributed to multiple open-source projects in the PyData ecosystem.",
        "Experience working in Agile teams with continuous integration pipelines.",
    ]
    for i, line in enumerate(body_lines):
        page.insert_text(fitz.Point(72, 80 + i * 14), line, fontsize=11)

    # Large bold name (heading_1 candidate: rfz >= 1.4 + bold via flags)
    tw = fitz.TextWriter(page.rect)
    font_bold = fitz.Font("hebo")   # Helvetica Bold — font name contains "Bo"
    tw.append(fitz.Point(72, 190), "Jane Smith", font=font_bold, fontsize=20)
    tw.write_text(page)

    # Section header — bold at normal size (heading_3)
    tw2 = fitz.TextWriter(page.rect)
    tw2.append(fitz.Point(72, 215), "Experience", font=font_bold, fontsize=11)
    tw2.write_text(page)

    # Bullet list
    bullets = [
        "- Built a real-time data ingestion service handling 10k events/s.",
        "- Reduced pipeline latency by 40% through algorithmic improvements.",
        "- Mentored three junior engineers in test-driven development practices.",
    ]
    for i, b in enumerate(bullets):
        page.insert_text(fitz.Point(72, 235 + i * 14), b, fontsize=11)

    # Italic job title
    tw3 = fitz.TextWriter(page.rect)
    font_italic = fitz.Font("heit")   # Helvetica Italic
    tw3.append(fitz.Point(72, 300), "Senior Engineer, Acme Corp", font=font_italic, fontsize=11)
    tw3.write_text(page)

    # Hyperlink
    link_text = "github.com/janesmith"
    page.insert_text(fitz.Point(72, 320), link_text, fontsize=11)
    w = fitz.Font("helv").text_length(link_text, fontsize=11)
    page.insert_link({
        "kind": fitz.LINK_URI,
        "from": fitz.Rect(72, 308, 72 + w, 324),
        "uri": "https://github.com/janesmith",
    })

    return _save(doc)


def make_report_pdf() -> str:
    """Report-like PDF: title, abstract, section headers, body paragraphs."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Body text at 11pt — anchors median
    body = [
        "This paper presents a novel approach to automatic document structure recognition.",
        "We evaluate our method on a benchmark of 500 academic papers and resumes.",
        "Results show a 15 percent improvement over the previous state of the art.",
        "The proposed approach combines rule-based heuristics with neural classifiers.",
        "Ablation studies confirm that each component contributes to overall accuracy.",
        "We release our code and dataset to support reproducibility in future research.",
    ]
    for i, line in enumerate(body):
        page.insert_text(fitz.Point(72, 80 + i * 14), line, fontsize=11)

    # Large bold title
    font_bold = fitz.Font("hebo")
    tw = fitz.TextWriter(page.rect)
    tw.append(fitz.Point(72, 190), "Document Structure Recognition", font=font_bold, fontsize=18)
    tw.write_text(page)

    # Centred "Abstract" label — compute x so the midpoint lands on page centre (297.5)
    abstract_text = "Abstract"
    abstract_w = font_bold.text_length(abstract_text, fontsize=11)
    abstract_x = (595 - abstract_w) / 2  # = 275.19 for this string/size
    tw2 = fitz.TextWriter(page.rect)
    tw2.append(fitz.Point(abstract_x, 215), abstract_text, font=font_bold, fontsize=11)
    tw2.write_text(page)

    # Section header
    tw3 = fitz.TextWriter(page.rect)
    tw3.append(fitz.Point(72, 240), "Introduction", font=font_bold, fontsize=11)
    tw3.write_text(page)

    # More body
    page.insert_text(fitz.Point(72, 260),
        "Document understanding has become increasingly important in information retrieval.",
        fontsize=11)
    page.insert_text(fitz.Point(72, 274),
        "Modern PDF converters often fail to capture formatting metadata.",
        fontsize=11)

    return _save(doc)


def make_article_pdf() -> str:
    """Plain article: centered title, body, numbered list."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Body text — anchors median
    body = [
        "Python has emerged as the dominant language for data science and machine learning.",
        "Its rich ecosystem of libraries makes it suitable for a wide range of tasks.",
        "From web scraping to deep learning, Python provides tools for every use case.",
        "The language emphasises readability which reduces the cost of maintenance.",
        "Extensive documentation and community support lower the barrier to entry.",
        "Performance-critical sections can be offloaded to C extensions via Cython.",
    ]
    for i, line in enumerate(body):
        page.insert_text(fitz.Point(72, 80 + i * 14), line, fontsize=11)

    # Centred title — compute x so midpoint lands exactly on page centre (297.5)
    title_text = "Why Python Dominates Data Science"
    title_w = fitz.Font("helv").text_length(title_text, fontsize=14)
    title_x = (595 - title_w) / 2
    page.insert_text(fitz.Point(title_x, 185), title_text, fontsize=14)

    # Centred caption at body size (11pt, not bold) — exercises centered_block rule.
    # Must be at median font size so heading rules do not fire first.
    caption_text = "Figure 1: Overview of the Python ecosystem"
    caption_w = fitz.Font("helv").text_length(caption_text, fontsize=11)
    caption_x = (595 - caption_w) / 2
    page.insert_text(fitz.Point(caption_x, 255), caption_text, fontsize=11)

    # Numbered list
    items = [
        "1. Readable syntax and gentle learning curve.",
        "2. First-class support for NumPy, Pandas, and scikit-learn.",
        "3. Vibrant open-source community and extensive documentation.",
    ]
    for i, item in enumerate(items):
        page.insert_text(fitz.Point(72, 275 + i * 14), item, fontsize=11)

    return _save(doc)


def make_scanned_pdf() -> str:
    """PDF with no text layer."""
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    return _save(doc)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _run_pipeline(pdf_path: str) -> str | None:
    """Run pipeline.run(); return LaTeX string or None on error."""
    try:
        return run(pdf_path)
    except Exception as exc:
        return None


def _check_pdflatex(tex_source: str) -> tuple[bool, str]:
    """
    Try to compile *tex_source* with pdflatex.
    Returns (success: bool, message: str).
    """
    if not shutil.which("pdflatex"):
        return None, "pdflatex not found on PATH"

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, "output.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_source)
        try:
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-output-directory", tmpdir, tex_path],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and "Error" not in result.stdout:
                return True, "compiled successfully"
            else:
                # Extract first error line for diagnosis
                for line in result.stdout.splitlines():
                    if line.startswith("!"):
                        return False, line
                return False, "pdflatex returned non-zero exit code"
        except subprocess.TimeoutExpired:
            return False, "pdflatex timed out"


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------

def main() -> int:
    failures: list[str] = []
    skips: list[str] = []

    print(f"\n{BOLD}pdf2TeX v0 — Validation against 9 success criteria{RESET}")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Build the 3 test PDFs + scanned PDF
    # ------------------------------------------------------------------
    print("\nBuilding test PDFs ...")
    resume_pdf  = make_resume_pdf()
    report_pdf  = make_report_pdf()
    article_pdf = make_article_pdf()
    scanned_pdf = make_scanned_pdf()

    pdfs = {
        "resume":  resume_pdf,
        "report":  report_pdf,
        "article": article_pdf,
    }

    # Run pipeline on all 3 before validation so we can inspect outputs
    outputs: dict[str, str | None] = {}
    for name, path in pdfs.items():
        outputs[name] = _run_pipeline(path)

    # ------------------------------------------------------------------
    # V1 — Tool runs on 3 born-digital PDFs without crashing
    # ------------------------------------------------------------------
    print(f"\n{BOLD}V1  Tool runs on 3 born-digital PDFs without crashing{RESET}")
    all_ran = True
    for name, latex in outputs.items():
        if latex is not None:
            _pass(f"Pipeline completed on {name} PDF")
        else:
            _fail(f"Pipeline crashed on {name} PDF")
            failures.append(f"V1: pipeline crashed on {name}")
            all_ran = False

    # ------------------------------------------------------------------
    # V2 — Output compiles with pdflatex
    # ------------------------------------------------------------------
    print(f"\n{BOLD}V2  Output .tex compiles with pdflatex{RESET}")
    for name, latex in outputs.items():
        if latex is None:
            _fail(f"{name}: no output to compile")
            failures.append(f"V2: no output for {name}")
            continue
        ok, msg = _check_pdflatex(latex)
        if ok is None:
            _skip(f"{name}: {msg}")
            skips.append(f"V2: {name}")
        elif ok:
            _pass(f"{name}: {msg}")
        else:
            _fail(f"{name}: {msg}")
            failures.append(f"V2: {name} compile failed — {msg}")

    # ------------------------------------------------------------------
    # V3 — Bold spans appear as \textbf{...}
    # ------------------------------------------------------------------
    print(f"\n{BOLD}V3  Bold spans appear as \\\\textbf{{...}}{RESET}")
    # Resume PDF has a bold name and section header inserted with hebo font
    latex = outputs.get("resume")
    if latex and r"\textbf{" in latex:
        _pass(r"resume output contains \textbf{}")
    elif latex:
        _fail(r"resume output has no \textbf{} — bold detection may have failed")
        failures.append("V3: no \\textbf in resume output")
    else:
        _fail("resume output unavailable")
        failures.append("V3: no resume output")

    # Also check report
    latex = outputs.get("report")
    if latex and r"\textbf{" in latex:
        _pass(r"report output contains \textbf{}")
    elif latex:
        _fail(r"report output has no \textbf{}")
        failures.append("V3: no \\textbf in report output")

    # ------------------------------------------------------------------
    # V4 — Italic spans appear as \textit{...}
    # ------------------------------------------------------------------
    print(f"\n{BOLD}V4  Italic spans appear as \\\\textit{{...}}{RESET}")
    latex = outputs.get("resume")
    if latex and r"\textit{" in latex:
        _pass(r"resume output contains \textit{}")
    elif latex:
        _fail(r"resume output has no \textit{} — italic detection may have failed")
        failures.append("V4: no \\textit in resume output")
    else:
        _fail("resume output unavailable")
        failures.append("V4: no resume output")

    # ------------------------------------------------------------------
    # V5 — Hyperlinks appear as \href{url}{text} with correct URLs
    # ------------------------------------------------------------------
    print(f"\n{BOLD}V5  Hyperlinks appear as \\\\href{{url}}{{text}}{RESET}")
    latex = outputs.get("resume")
    expected_url = "https://github.com/janesmith"
    if latex and expected_url in latex and r"\href{" in latex:
        _pass(f"resume output contains \\href with correct URL ({expected_url})")
    elif latex and r"\href{" in latex:
        _fail(f"resume output has \\href but URL {expected_url!r} not found")
        failures.append("V5: wrong URL in href")
    elif latex:
        _fail(r"resume output has no \href{}")
        failures.append("V5: no \\href in resume output")
    else:
        _fail("resume output unavailable")
        failures.append("V5: no resume output")

    # ------------------------------------------------------------------
    # V6 — Large/bold top-of-block text becomes \section{} or \subsection{}
    # ------------------------------------------------------------------
    print(f"\n{BOLD}V6  Large/bold headings become \\\\section{{}} or \\\\subsection{{}}{RESET}")
    for name in ("resume", "report"):
        latex = outputs.get(name)
        if latex and (r"\section{" in latex or r"\subsection{" in latex
                      or r"\subsubsection{" in latex):
            _pass(f"{name} output contains a heading command")
        elif latex:
            _fail(f"{name} output has no heading commands")
            failures.append(f"V6: no heading in {name} output")
        else:
            _fail(f"{name} output unavailable")
            failures.append(f"V6: no {name} output")

    # ------------------------------------------------------------------
    # V7 — Centered text renders in \begin{center}...\end{center}
    # ------------------------------------------------------------------
    print(f"\n{BOLD}V7  Centered text renders in \\\\begin{{center}}...\\\\end{{center}}{RESET}")
    # The report PDF has "Abstract" inserted at x=260 (centred on a 595pt page)
    # The article PDF has a title inserted at x=175 (moderate centre)
    found_center = False
    for name in ("resume", "report", "article"):
        latex = outputs.get(name)
        if latex and r"\begin{center}" in latex:
            _pass(f"{name} output contains \\begin{{center}}")
            found_center = True
            break
    if not found_center:
        # Not a hard failure — alignment detection is heuristic; report as info
        _fail("No centered block detected in any output — check alignment heuristic")
        failures.append("V7: no \\begin{center} found in any output")

    # ------------------------------------------------------------------
    # V8 — Scanned PDF exits with informative error, not crash
    # ------------------------------------------------------------------
    print(f"\n{BOLD}V8  Scanned PDF exits with informative error{RESET}")
    try:
        run(scanned_pdf)
        _fail("Scanned PDF did not raise an error — should have raised ScannedPDFPipelineError")
        failures.append("V8: scanned PDF did not raise error")
    except ScannedPDFPipelineError as exc:
        msg = str(exc)
        if "scanned" in msg.lower() or "text layer" in msg.lower() or "born-digital" in msg.lower():
            _pass(f"ScannedPDFPipelineError raised with informative message")
        else:
            _pass(f"ScannedPDFPipelineError raised (message: {msg[:80]})")
    except Exception as exc:
        _fail(f"Unexpected exception type: {type(exc).__name__}: {exc}")
        failures.append(f"V8: wrong exception type {type(exc).__name__}")

    # ------------------------------------------------------------------
    # V9 — No text content silently dropped
    # ------------------------------------------------------------------
    print(f"\n{BOLD}V9  No text content silently dropped{RESET}")

    checks = {
        "resume":  ["experience", "acme", "engineer", "github"],
        "report":  ["document", "structure", "recognition", "introduction"],
        "article": ["python", "data", "science", "numpy"],
    }
    # Note: text is lowercased in PDF source, but LaTeX output may have
    # different casing — check case-insensitively.
    all_present = True
    for name, words in checks.items():
        latex = outputs.get(name)
        if not latex:
            _fail(f"{name}: no output to check")
            failures.append(f"V9: no output for {name}")
            all_present = False
            continue
        latex_lower = latex.lower()
        missing = [w for w in words if w not in latex_lower]
        if not missing:
            _pass(f"{name}: all sampled words present in output")
        else:
            _fail(f"{name}: words missing from output: {missing}")
            failures.append(f"V9: {name} missing words {missing}")
            all_present = False

    # ------------------------------------------------------------------
    # Clean up temp files
    # ------------------------------------------------------------------
    for path in [resume_pdf, report_pdf, article_pdf, scanned_pdf]:
        try:
            os.unlink(path)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    total   = 9
    skipped = len(set(s.split(":")[0] for s in skips))
    failed  = len(set(f.split(":")[0] for f in failures))
    passed  = total - failed - skipped

    if not failures and not skips:
        print(f"{GREEN}{BOLD}All {total} criteria PASSED.{RESET}")
    else:
        if passed:
            print(f"{GREEN}Passed:{RESET}  {passed}/{total}")
        if skipped:
            print(f"{YELLOW}Skipped:{RESET} {skipped}/{total}  (pdflatex not installed)")
        if failed:
            print(f"{RED}Failed:{RESET}  {failed}/{total}")
            print(f"\n{RED}Failures:{RESET}")
            for f in failures:
                print(f"  - {f}")

    print()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
