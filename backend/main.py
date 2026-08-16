"""
main.py — FastAPI application entry point.

Endpoints:
  GET  /           → serves frontend/index.html
  GET  /languages  → list of supported language names
  POST /generate   → run pipeline, return .docx download

Run with:
  uvicorn backend.main:app --reload
"""

import asyncio
import base64
import io
import json
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Import pipeline steps
from backend.generator import generate_theory_and_code, fix_code
from backend.executor import run_code, run_code_stream
from backend.renderer import render_terminal, warmup_browser
from backend.assembler import assemble_document

# In-memory store for generated .docx files from stream requests
_generated_files: dict[str, dict] = {}


def _sse_event(event_type: str, message: str, data: dict = None) -> str:
    payload = {
        "type": event_type,
        "message": message,
        "timestamp": time.strftime("%H:%M:%S"),
    }
    if data is not None:
        payload["data"] = data
    return f"data: {json.dumps(payload)}\n\n"


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
    warmup_browser() dispatches to the dedicated playwright thread
    internally, so it is safe to call directly from async context.
    """
    warmup_browser()   # blocks until Chromium is ready
    yield              # server runs; browser stays alive until shutdown

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
    api_key: str = ""   # optional user-supplied Gemini API key


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
            req.aim, req.language, req.code_instructions, req.theory_instructions,
            api_key=req.api_key.strip() or None
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


@app.get("/download/{file_id}")
def download_generated_file(file_id: str):
    """Download a generated DOCX file by its stream file_id."""
    file_info = _generated_files.get(file_id)
    if not file_info:
        raise HTTPException(status_code=404, detail="File not found or download link expired.")
    return Response(
        content=file_info["bytes"],
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{file_info["filename"]}"'
        },
    )


@app.post("/generate-stream")
async def generate_experiment_stream(req: GenerateRequest):
    """
    Real-time Server-Sent Events (SSE) streaming pipeline.
    Emits live status updates, code output line-by-line, Playwright browser screenshot,
    and final DOCX download link.
    """
    if not req.aim.strip():
        raise HTTPException(status_code=400, detail="Aim cannot be empty.")
    if req.experiment_number < 1:
        raise HTTPException(status_code=400, detail="Experiment number must be ≥ 1.")

    blocked_reason = _validate_aim(req.aim)
    if blocked_reason:
        raise HTTPException(status_code=400, detail=f"Your experiment aim contains {blocked_reason}.")

    if req.code_instructions.strip():
        blocked_reason = _validate_aim(req.code_instructions)
        if blocked_reason:
            raise HTTPException(status_code=400, detail=f"Your code instructions contain {blocked_reason}.")

    async def event_generator():
        try:
            yield _sse_event("agent_started", "AI Agent initialized. Processing task...")
            await asyncio.sleep(0.2)

            # ── 1. Gemini theory + code ─────────────────────────────────────────
            yield _sse_event("generating_code", "Generating theory and source code with Gemini...")
            api_key = req.api_key.strip() or None
            content = await asyncio.to_thread(
                generate_theory_and_code,
                req.aim, req.language, req.code_instructions, req.theory_instructions, api_key=api_key
            )

            theory = content["theory"]
            final_code = content["code"]
            software = content["software"]

            yield _sse_event("code_generated", "Theory and code generated successfully", data={
                "code": final_code,
                "theory": theory,
                "software": software,
            })
            await asyncio.sleep(0.2)

            # ── 2. Sandbox execution & streaming ──────────────────────────────
            yield _sse_event("sandbox_starting", "Initializing isolated sandbox environment...")
            yield _sse_event("execution_started", f"Executing {req.language} program in sandbox...")

            stdout, stderr = "", ""
            plot_png = None

            def _stream_runner():
                return list(run_code_stream(final_code, req.language))

            events = await asyncio.to_thread(_stream_runner)

            for ev in events:
                if ev["type"] in ("log", "stdout"):
                    yield _sse_event("terminal_output", ev.get("text", ""))
                    await asyncio.sleep(0.02)
                elif ev["type"] == "result":
                    stdout = ev.get("stdout", "")
                    stderr = ev.get("stderr", "")
                    plot_png = ev.get("plot_png")

            # Retry / fix loop if stderr
            if stderr and not stdout:
                for attempt in range(2):
                    yield _sse_event("terminal_output", f"\n[Attempt {attempt+2}] Fixing code error with Gemini...\n")
                    try:
                        final_code = await asyncio.to_thread(fix_code, final_code, stderr, req.aim, req.language)
                        yield _sse_event("code_generated", f"Code auto-corrected (Attempt {attempt+2})", data={"code": final_code})
                        retry_events = await asyncio.to_thread(lambda: list(run_code_stream(final_code, req.language)))
                        for ev in retry_events:
                            if ev["type"] in ("log", "stdout"):
                                yield _sse_event("terminal_output", ev.get("text", ""))
                                await asyncio.sleep(0.02)
                            elif ev["type"] == "result":
                                stdout = ev.get("stdout", "")
                                stderr = ev.get("stderr", "")
                                plot_png = ev.get("plot_png")
                        if not stderr:
                            break
                    except Exception:
                        pass

            output_text = stdout if stdout else (stderr if stderr else "(No output produced)")

            yield _sse_event("execution_completed", "Code execution completed", data={
                "stdout": stdout,
                "stderr": stderr,
                "output_text": output_text,
            })
            await asyncio.sleep(0.2)

            # ── 3. Playwright Terminal Screenshot ─────────────────────────────
            yield _sse_event("playwright_starting", "Launching Playwright renderer...")
            terminal_png = await asyncio.to_thread(render_terminal, output_text.strip(), req.language)
            img_b64 = base64.b64encode(terminal_png).decode("utf-8")

            yield _sse_event("browser_screenshot", "Captured high-res terminal screenshot preview", data={
                "image": img_b64,
            })
            await asyncio.sleep(0.2)

            # ── 4. Assemble Word DOCX ─────────────────────────────────────────
            yield _sse_event("document_generation", "Assembling Word document (.docx)...")
            docx_bytes = await asyncio.to_thread(
                assemble_document,
                experiment_number=req.experiment_number,
                aim=req.aim,
                theory=theory,
                code=final_code,
                terminal_png=terminal_png,
                software=software,
                plot_png=plot_png,
            )

            file_id = str(uuid.uuid4())
            filename = f"Experiment_{req.experiment_number}.docx"
            _generated_files[file_id] = {
                "bytes": docx_bytes,
                "filename": filename,
                "created_at": time.time(),
            }

            yield _sse_event("completed", "Word document generated successfully!", data={
                "download_url": f"/download/{file_id}",
                "filename": filename,
            })

        except Exception as exc:
            yield _sse_event("error", f"Generation failed: {str(exc)}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

