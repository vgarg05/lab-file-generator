# Automated Lab File Generator — Architecture

## Overview

Input: an experiment **aim** (e.g., "WAP to implement Bubble Sort") + target **language**.
Output: a completed lab experiment document (DOCX/PDF) with Aim, Theory, Code, and Terminal Output sections filled in — for one experiment or batched across many, into a single lab file.

```
Aim + Language
      │
      ▼
[1] Content Generation (LLM)
      │  → Theory text
      │  → Source code
      ▼
[2] Code Execution (Sandbox)
      │  → stdout / stderr
      │  → retry loop on error
      ▼
[3] Terminal Rendering
      │  → styled "terminal" PNG from output text
      ▼
[4] Document Assembly
      │  → fill placeholders in template
      │  → repeat 1-3 per experiment
      ▼
[5] Export
      → DOCX → PDF (single lab file, multiple experiments)
```

---

## 1. Content Generation

**Component:** LLM call (Gemini API, or any LLM you're already using)

- **Input:** aim, language, optional style/length hints
- **Output:** theory text, source code
- Two separate prompts (or one structured-JSON prompt) — one for theory, one for code — so each can be regenerated independently without re-running the other.
- Use few-shot examples matching your college's expected theory tone/length (concise, textbook-style) for consistency across experiments.
- Structured output (JSON mode) recommended so `theory` and `code` land in predictable fields, no parsing guesswork.

---

## 2. Code Execution (Sandbox)

**Component:** Per-language Docker containers, or a hosted execution API (e.g., Piston, Judge0)

- Executes generated code safely, isolated from host machine.
- Captures `stdout` + `stderr`.
- **Retry loop:** if `stderr` is non-empty → feed the error back to the LLM with the original code → regenerate → re-run. Cap at ~3 attempts, then flag for manual review.
- Supports multiple languages (C, C++, Java, Python, etc.) via separate container images or an execution API that already supports multi-language.

---

## 3. Terminal Output Rendering

**Component:** Terminal-style renderer (not a real screenshot)

- Render captured stdout/stderr into a styled terminal-look image.
- Options:
  - HTML/CSS terminal mockup + headless browser screenshot (Playwright/Puppeteer)
  - Python `rich` library → export to PNG
  - `termshot` / `carbon-now-sh`-style renderers
- Output: a PNG that looks like a real terminal window, scriptable and consistent — no OS-dependent screenshot fragility.

---

## 4. Document Assembly

**Component:** `python-docx`

- Template `.docx` with placeholders: `{{AIM}}`, `{{THEORY}}`, `{{CODE}}`, `{{OUTPUT_IMAGE}}`
- Code block inserted with syntax highlighting (via `pygments`, rendered as formatted text or image).
- Terminal PNG from step 3 inserted at `{{OUTPUT_IMAGE}}`.
- For a full lab file: loop this per experiment, appending each filled section (with page breaks) into one combined document.

---

## 5. Export

**Component:** `docx2pdf` or `libreoffice --headless --convert-to pdf`

- Converts the final combined DOCX into a single PDF lab file.

---

## Orchestration

A single Python script or lightweight FastAPI backend chaining steps 1→5, optionally wrapped in a Streamlit/Gradio UI:

```
POST /generate-experiment
  { aim, language }
  → runs steps 1-5
  → returns experiment PDF/DOCX

POST /generate-lab-file
  { [ {aim, language}, {aim, language}, ... ] }
  → runs steps 1-5 per experiment
  → returns combined lab file PDF
```

---

## Key Risks / Design Decisions

| Concern | Mitigation |
|---|---|
| LLM-generated code may fail on first run | Error-feedback retry loop (step 2) |
| Running arbitrary code is unsafe | Docker sandbox per language, or hosted execution API |
| Real terminal screenshots are OS-fragile | Render styled terminal image from captured text instead |
| Theory tone/length inconsistent with college format | Few-shot prompt examples matching expected style |
| Multi-experiment formatting drift | Single template, looped programmatically, not hand-edited per experiment |

---

## Suggested Stack

- **Generation:** Gemini API
- **Execution:** Docker (per-language images) or Piston/Judge0 API
- **Terminal rendering:** Playwright + HTML/CSS terminal template, or Python `rich`
- **Document:** `python-docx` + LibreOffice headless (PDF conversion)
- **Orchestration/UI:** FastAPI backend + Streamlit/Gradio front end
