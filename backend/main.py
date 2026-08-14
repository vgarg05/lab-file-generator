"""
main.py — FastAPI application entry point.

Endpoints:
  GET  /           → serves frontend/index.html
  GET  /languages  → list of supported language names
  POST /generate   → run pipeline, return .docx download

Run with:
  uvicorn backend.main:app --reload
"""

import io
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Import pipeline steps
from backend.generator import generate_theory_and_code, fix_code
from backend.executor import run_code
from backend.renderer import render_terminal, _get_browser
from backend.assembler import assemble_document

# ── Dangerous aim keyword filter ────────────────────────────────────────────
# Each entry: (regex_pattern, human_readable_reason)
DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\brmtree\b",           "file/directory deletion commands (rmtree)"),
    (r"\bshutil\.rm",         "file/directory deletion commands (shutil.rm)"),
    (r"\bos\.remove\b",       "file deletion commands (os.remove)"),
    (r"\bos\.system\b",       "direct OS shell execution (os.system)"),
    (r"\bsubprocess\.call\b", "direct shell subprocess execution"),
    (r"\bsubprocess\.run\b",  "direct shell subprocess execution"),
    (r"\bsubprocess\.Popen\b","direct shell subprocess execution"),
    (r"\bdrop\s+database\b",  "destructive database commands (DROP DATABASE)"),
    (r"\bdrop\s+table\b",     "destructive database commands (DROP TABLE)"),
    (r"/etc/passwd",          "access to sensitive system files (/etc/passwd)"),
    (r"\brm\s+-rf\b",         "dangerous shell command (rm -rf)"),
    (r"\bformat\s+[cCdDeEfF]:","disk formatting command"),
    (r"\b__import__\b",       "dynamic import execution tricks"),
    (r"\beval\s*\(",           "arbitrary code execution via eval()"),
    (r"\bexec\s*\(",           "arbitrary code execution via exec()"),
]


def _validate_aim(aim: str) -> str | None:
    """
    Check the aim text for dangerous keywords.
    Returns a human-readable reason string if blocked, else None.
    """
    aim_lower = aim.lower()
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, aim_lower, re.IGNORECASE):
            return reason
    return None

# ── App setup ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Warm up Chromium at server startup so the first user never
    waits for a cold-start browser launch during generation.
    """
    _get_browser()          # launches Chromium once in the background
    yield                   # server is now running and serving requests
                            # (browser stays alive until server shuts down)

app = FastAPI(title="Lab File Generator", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolve frontend directory relative to this file
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# Serve frontend static files at /static/*
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── Request model ─────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    experiment_number: int
    aim: str
    language: str
    code_instructions: str = ""
    theory_instructions: str = ""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    """Serve the main frontend page."""
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/languages")
def get_languages():
    """Return the list of supported programming languages."""
    return {"languages": ["Python", "C", "C++", "Java", "JavaScript", "Rust"]}


@app.post("/generate")
def generate_experiment(req: GenerateRequest):
    """
    Full pipeline: aim + language → DOCX file download.

    Pipeline:
      1. Gemini → theory + code (JSON mode)
      2. Piston API → execute code (retry up to 3x on error)
      3. Playwright → terminal PNG
      4. python-docx → assemble DOCX
      5. Stream DOCX as file download response
    """
    # ── Validate ──────────────────────────────────────────────────────────────────────
    if not req.aim.strip():
        raise HTTPException(status_code=400, detail="Aim cannot be empty.")
    if req.experiment_number < 1:
        raise HTTPException(status_code=400, detail="Experiment number must be ≥ 1.")

    # ── Aim safety check ────────────────────────────────────────────────────────────
    blocked_reason = _validate_aim(req.aim)
    if blocked_reason:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Your aim was not accepted because it contains {blocked_reason}. "
                f"Please describe a standard programming experiment "
                f"(e.g., 'Write a program to implement Bubble Sort')."
            ),
        )

    # ── Code instructions safety check ──────────────────────────────────────────────
    if req.code_instructions.strip():
        blocked_reason = _validate_aim(req.code_instructions)
        if blocked_reason:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Your code instructions were not accepted because they contain "
                    f"{blocked_reason}. Please provide standard programming guidelines "
                    f"(e.g., 'Use recursion' or 'Format output as a table')."
                ),
            )

    # ── Step 1: Generate theory + code ───────────────────────────────────────────────
    try:
        content = generate_theory_and_code(
            req.aim, req.language, req.code_instructions, req.theory_instructions
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Content generation failed: {exc}")

    theory = content["theory"]
    final_code = content["code"]
    software = content["software"]

    # ── Step 2: Execute with retry loop ───────────────────────────────────────
    stdout, stderr = "", ""
    plot_png = None
    for attempt in range(3):
        result = run_code(final_code, req.language)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        plot_png = result.get("plot_png")

        if not stderr:
            break  # Success

        # Still have attempts left — ask Gemini to fix the code
        if attempt < 2:
            try:
                final_code = fix_code(final_code, stderr, req.aim, req.language)
            except Exception:
                pass  # Keep existing code; try running again

    # Use stdout; fall back to stderr if nothing in stdout (runtime partial output, etc.)
    output_text = stdout if stdout else (stderr if stderr else "(No output produced)")

    # ── Step 3: Render terminal PNG ───────────────────────────────────────────
    try:
        terminal_png = render_terminal(output_text.strip(), req.language)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Terminal rendering failed: {exc}")

    # ── Step 4: Assemble DOCX ─────────────────────────────────────────────────
    try:
        docx_bytes = assemble_document(
            experiment_number=req.experiment_number,
            aim=req.aim,
            theory=theory,
            code=final_code,
            terminal_png=terminal_png,
            software=software,
            plot_png=plot_png,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Document assembly failed: {exc}")

    # ── Step 5: Stream DOCX response ──────────────────────────────────────────
    filename = f"Experiment_{req.experiment_number}.docx"
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Experiment-Number": str(req.experiment_number),
        },
    )
