/* pdf2TeX — frontend logic */

"use strict";

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const dropZone     = document.getElementById("drop-zone");
const fileInput    = document.getElementById("file-input");
const uploadBtn    = document.getElementById("upload-btn");
const statusBar    = document.getElementById("status-bar");
const statusMsg    = document.getElementById("status-msg");
const errorAlert   = document.getElementById("error-alert");
const resultSection = document.getElementById("result-section");
const texPreview   = document.getElementById("tex-preview");
const downloadBtn  = document.getElementById("download-btn");
const convertAgain = document.getElementById("convert-again");
const lineCount    = document.getElementById("line-count");
const fileLabel    = document.getElementById("file-label");

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let currentJobId = null;
let pollTimer    = null;

// ---------------------------------------------------------------------------
// Drag-and-drop
// ---------------------------------------------------------------------------
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("drag-over");
});

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});

dropZone.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) handleFile(fileInput.files[0]);
});

// ---------------------------------------------------------------------------
// File selection
// ---------------------------------------------------------------------------
function handleFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showError("Only PDF files are supported.");
    return;
  }
  resetUI();
  fileLabel.textContent = file.name;
  uploadBtn.disabled = false;
  uploadBtn.onclick = () => uploadFile(file);
}

// ---------------------------------------------------------------------------
// Upload & poll
// ---------------------------------------------------------------------------
async function uploadFile(file) {
  uploadBtn.disabled = true;
  hideError();
  showStatus("Uploading …");

  const formData = new FormData();
  formData.append("file", file);

  let jobId;
  try {
    const res = await fetch("/upload", { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Upload failed.");
    }
    const data = await res.json();
    jobId = data.job_id;
    currentJobId = jobId;
  } catch (err) {
    showError(err.message);
    uploadBtn.disabled = false;
    hideStatus();
    return;
  }

  showStatus("Running pipeline …");
  pollTimer = setInterval(() => pollResult(jobId), 800);
}

async function pollResult(jobId) {
  try {
    const res = await fetch(`/result/${jobId}`);
    if (!res.ok) return;
    const data = await res.json();

    if (data.status === "running" || data.status === "pending") {
      showStatus(data.status === "pending" ? "Queued …" : "Running pipeline …");
      return;
    }

    clearInterval(pollTimer);
    pollTimer = null;

    if (data.status === "error") {
      showError(data.error || "An error occurred.");
      hideStatus();
      uploadBtn.disabled = false;
      return;
    }

    if (data.status === "done") {
      hideStatus();
      showResult(data.latex, data.line_count, jobId);
    }
  } catch (_) {
    // network hiccup — keep polling
  }
}

// ---------------------------------------------------------------------------
// Result rendering
// ---------------------------------------------------------------------------
function showResult(latex, lines, jobId) {
  texPreview.innerHTML = highlightLatex(escapeHtml(latex));
  lineCount.textContent = `${lines} lines`;
  downloadBtn.href = `/download/${jobId}`;
  resultSection.classList.add("visible");
  resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------------------------------------------------------------------------
// Minimal LaTeX syntax highlighter
// ---------------------------------------------------------------------------
function highlightLatex(escaped) {
  // Order matters — most specific first
  return escaped
    // % comments
    .replace(/(%.*)$/gm, '<span class="com">$1</span>')
    // \begin{env} and \end{env}
    .replace(/(\\(?:begin|end))\{([^}]*)\}/g,
      '<span class="env">$1</span>{<span class="arg">$2</span>}')
    // \command (backslash + word chars)
    .replace(/\\([a-zA-Z]+)/g, '<span class="kw">\\$1</span>')
    // remaining {content} arguments (after commands are already highlighted)
    .replace(/\{([^}]*)\}/g, '{<span class="arg">$1</span>}');
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ---------------------------------------------------------------------------
// UI helpers
// ---------------------------------------------------------------------------
function showStatus(msg) {
  statusMsg.textContent = msg;
  statusBar.classList.add("visible");
}

function hideStatus() {
  statusBar.classList.remove("visible");
}

function showError(msg) {
  errorAlert.textContent = msg;
  errorAlert.classList.add("visible");
}

function hideError() {
  errorAlert.classList.remove("visible");
}

function resetUI() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  currentJobId = null;
  hideStatus();
  hideError();
  resultSection.classList.remove("visible");
  texPreview.innerHTML = "";
  uploadBtn.disabled = true;
  fileLabel.textContent = "";
}

// "Convert another file" button
convertAgain.addEventListener("click", () => {
  resetUI();
  fileInput.value = "";
  dropZone.scrollIntoView({ behavior: "smooth" });
});
