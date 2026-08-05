"""
web/app.py
----------
FastAPI backend for the pdf2TeX web UI.

Endpoints
---------
POST /upload          Accept a PDF, run the pipeline, return job ID
GET  /result/{job_id} Poll for result — returns status + LaTeX when ready
GET  /download/{job_id} Download the .tex file
GET  /                Serve the single-page UI
GET  /static/*        Serve static assets
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

# Ensure the project root is importable regardless of cwd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdf_to_latex.pipeline import (
    EmptyDocumentError,
    ScannedPDFPipelineError,
    run as pipeline_run,
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="pdf2TeX", version="0.1.0")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ---------------------------------------------------------------------------
# In-memory job store
# Simple dict is fine for a single-process dev server.
# Replace with Redis / DB for production.
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}
# Job schema:
# {
#   "status": "pending" | "running" | "done" | "error",
#   "filename": str,
#   "latex": str | None,
#   "error": str | None,
# }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve the single-page UI."""
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    """
    Accept a PDF upload, start the pipeline in a background thread,
    and return a job_id for polling.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "pending",
        "filename": file.filename,
        "latex": None,
        "error": None,
    }

    # Read file bytes before the async context closes
    pdf_bytes = await file.read()

    # Run pipeline in a background thread (pipeline is CPU-bound / blocking I/O)
    thread = threading.Thread(
        target=_run_pipeline_job,
        args=(job_id, pdf_bytes, file.filename),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "filename": file.filename}


@app.get("/result/{job_id}")
async def result(job_id: str) -> dict:
    """
    Poll for job status.

    Returns:
        {
          "status": "pending" | "running" | "done" | "error",
          "filename": str,
          "latex": str | null,   # populated when status == "done"
          "error": str | null,   # populated when status == "error"
          "line_count": int | null
        }
    """
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    latex = job.get("latex")
    return {
        "status":     job["status"],
        "filename":   job["filename"],
        "latex":      latex,
        "error":      job.get("error"),
        "line_count": latex.count("\n") if latex else None,
    }


@app.get("/download/{job_id}")
async def download(job_id: str) -> FileResponse:
    """
    Download the generated .tex file for a completed job.
    """
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] != "done" or not job["latex"]:
        raise HTTPException(status_code=400, detail="Job not complete yet.")

    # Write to a named temp file so FileResponse can stream it
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".tex", delete=False, encoding="utf-8"
    )
    tmp.write(job["latex"])
    tmp.close()

    stem = Path(job["filename"]).stem
    return FileResponse(
        path=tmp.name,
        media_type="text/plain",
        filename=f"{stem}.tex",
        background=None,
    )


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

def _run_pipeline_job(job_id: str, pdf_bytes: bytes, filename: str) -> None:
    """Run the pipeline in a background thread and update the job store."""
    _jobs[job_id]["status"] = "running"

    # Write bytes to a temp file (pipeline expects a file path)
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        tmp.write(pdf_bytes)
        tmp.close()
        latex = pipeline_run(tmp.name)
        _jobs[job_id]["latex"] = latex
        _jobs[job_id]["status"] = "done"
    except ScannedPDFPipelineError as exc:
        _jobs[job_id]["error"] = (
            "This PDF appears to be scanned or image-only. "
            "pdf2TeX v0 requires a born-digital PDF with an extractable text layer."
        )
        _jobs[job_id]["status"] = "error"
    except EmptyDocumentError as exc:
        _jobs[job_id]["error"] = str(exc)
        _jobs[job_id]["status"] = "error"
    except Exception as exc:
        _jobs[job_id]["error"] = f"Unexpected error: {exc}"
        _jobs[job_id]["status"] = "error"
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
