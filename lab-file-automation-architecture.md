# Automated Lab File Generator — Architecture

## Overview

**Input:** Experiment **Number**, Experiment **Aim**, **Language**, and optional **Additional Instructions**.  
**Output:** A formatted `.docx` lab report containing **Aim**, **Software Used**, **Theory**, **Source Code**, and **Output** (VS Code Terminal screenshot + embedded Matplotlib plots if generated).

```
Aim + Language + Extra Instructions
             │
             ▼
[1] Content Generation (Gemini 3.1 Flash Lite)
             │  → Software Used
             │  → Theory text
             │  → Source Code
             ▼
[2] Subprocess Code Execution (Local / Linux Sandbox)
             │  → Safety & RAM Scanners
             │  → Matplotlib Plot Capture
             │  → stdout / stderr
             │  → Self-Healing retry loop on error (max 3 retries)
             ▼
[3] VS Code Terminal Rendering (Playwright)
             │  → Styled VS Code dark terminal PNG from output text
             ▼
[4] In-Memory Document Assembly (python-docx)
             │  → Times New Roman typography & standard margins
             │  → Inline Aim, Software Used, Theory, Code
             │  → Terminal PNG & Matplotlib Plot embedding
             ▼
[5] Export / Download
             → Downloadable .docx file (generated completely in-memory)
```

---

## 1. Content Generation

**Component:** LLM call (`gemini-3.1-flash-lite` via `google-generativeai`)

- **Input:** Experiment Aim, Programming Language, and optional user instructions (e.g. *"Use recursion"*, *"Explain time complexity"*).
- **Output:** Structured JSON containing `software_used`, `theory`, and `code`.
- **JSON Schema Enforcement:** Prompts mandate strict JSON structure to prevent output parsing failures.
- **Self-Healing Loop:** If code fails during execution, a secondary prompt feeds the original code and exact error back to Gemini to request a corrected version.

---

## 2. Code Execution & Security Sandbox

**Component:** Local Subprocess Runner (`backend/executor.py`)

- Runs generated code safely using local environment runtimes (`python`, `gcc`, `g++`, `javac`, `node`, `rustc`).
- **Security & Safety Guardrails:**
  - **Dangerous Code Scanner:** Scans for forbidden patterns (`os.remove`, `shutil.rmtree`, `subprocess`, `/etc/passwd`) before execution.
  - **Memory Protection Scanner:** Flags heavy packages (`TensorFlow`, `PyTorch`) that exceed free-tier RAM limits.
  - **Linux Security Isolation:** On Linux production servers (e.g., Render), process privileges drop to the unprivileged `nobody` user.
- **Plot Capture:** Monkeypatches `matplotlib.pyplot.savefig` to automatically capture generated charts to `plot.png` without crashing headlessly.
- **Self-Healing Retry Loop:** If execution fails (`stderr` non-empty or non-zero exit code), the error is returned to Gemini for automated repair (up to 3 attempts).

---

## 3. Terminal Output Rendering

**Component:** Playwright + HTML/CSS Terminal Template (`backend/renderer.py`)

- Renders captured `stdout` and `stderr` into an HTML template (`backend/templates/terminal.html`) styled like a VS Code dark-mode terminal.
- **Playwright Headless Browser:** Takes a high-resolution element screenshot (`#terminal`) to output a crisp `terminal.png`.
- Ensures clean, consistent, cross-platform terminal visual output independent of host OS styling.

---

## 4. Document Assembly

**Component:** `python-docx` (`backend/assembler.py`)

- Assembles the complete document in-memory into a `BytesIO` buffer — zero temporary files written to disk.
- Applies standard styling:
  - **Title:** `Experiment - N` (Times New Roman 16pt Bold, Centered)
  - **Aim & Software Used:** Inline bold headers (16pt) with content (14pt)
  - **Theory & Code:** Headings (16pt Bold) followed by formatted content (14pt)
  - **Output Section:** Embeds the rendered `terminal.png` image and optional `plot.png` chart image.

---

## 5. Deployment & Orchestration

**Backend:** FastAPI + Uvicorn hosting single endpoints (`POST /api/generate`)  
**Frontend:** Vanilla HTML/CSS/JS SaaS interface with live progress indicators  
**Production Hosting:** Deployed on Render with headless Playwright Chromium and compiler toolchains  

---

## Key Risks / Design Decisions

| Concern | Mitigation |
|---|---|
| Generated code fails compilation/runtime | Self-healing LLM error repair loop (up to 3 retries) |
| Arbitrary code execution risks on server | Pre-execution pattern scanners + Linux `nobody` unprivileged user drop |
| Heavy ML models crash server memory | Pre-execution scanner detects heavy libraries (PyTorch/TF) and advises local execution |
| Matplotlib popups block server thread | Headless `Agg` backend monkeypatch forces savefig to in-memory bytes |
| Terminal screenshot OS inconsistency | HTML/CSS VS Code mockup captured via headless Playwright |

---

## Suggested / Actual Stack

- **LLM:** Google Gemini 3.1 Flash Lite
- **Backend:** FastAPI + Uvicorn
- **Code Execution:** Local Subprocess Sandbox + Custom Security Scanners
- **Terminal Renderer:** Playwright + HTML/CSS
- **Document Builder:** `python-docx`
- **Frontend:** Vanilla HTML5 / CSS3 / JS

---

## ⚠️ Disclaimer

This architecture and project were developed strictly for educational and portfolio demonstration purposes to explore LLM integration, automated code execution, and programmatic document assembly. It is not intended to bypass academic integrity policies.

