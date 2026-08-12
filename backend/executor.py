"""
executor.py — Local subprocess code execution.

Runs generated code directly on the host machine using locally installed
compilers / interpreters. No API keys, no internet, no limits.

Requirements:
  - Python:     python or python3 on PATH
  - C:          gcc on PATH
  - C++:        g++ on PATH
  - Java:       javac + java on PATH
  - JavaScript: node on PATH
  - Rust:       rustc on PATH
"""

import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path

# Per-language config:
#   filename  — what to save the source as
#   compile   — compile command (None if interpreted)
#   run       — run command
#   exe_name  — name of the compiled binary (None if interpreted)
LANGUAGE_CONFIG: dict[str, dict] = {
    "Python": {
        "filename": "main.py",
        "compile": None,
        "run": [sys.executable, "main.py"],  # same .venv Python running the server
        "exe_name": None,
    },
    "C": {
        "filename": "main.c",
        "compile": ["gcc", "main.c", "-o", "main.exe", "-lm"],
        "run": ["main.exe"],
        "exe_name": "main.exe",
    },
    "C++": {
        "filename": "main.cpp",
        "compile": ["g++", "main.cpp", "-o", "main.exe", "-lm"],
        "run": ["main.exe"],
        "exe_name": "main.exe",
    },
    "Java": {
        "filename": "Main.java",
        "compile": ["javac", "Main.java"],
        "run": ["java", "Main"],
        "exe_name": None,
    },
    "JavaScript": {
        "filename": "main.js",
        "compile": None,
        "run": ["node", "main.js"],
        "exe_name": None,
    },
    "Rust": {
        "filename": "main.rs",
        "compile": ["rustc", "main.rs", "-o", "main.exe"],
        "run": ["main.exe"],
        "exe_name": "main.exe",
    },
}

# Timeouts (seconds)
COMPILE_TIMEOUT = 30
RUN_TIMEOUT = 30


def run_code(code: str, language: str) -> dict:
    """
    Execute code locally via subprocess.

    Args:
        code:     Source code string.
        language: User-facing language name (e.g. "Python", "C++").

    Returns:
        dict with "stdout" (str) and "stderr" (str).
        Empty stderr means the run was successful.
    """
    config = LANGUAGE_CONFIG.get(language)
    if config is None:
        return {
            "stdout": "",
            "stderr": f"Unsupported language: {language}. "
            f"Supported: {', '.join(LANGUAGE_CONFIG.keys())}",
        }

    # Create a temporary directory for this execution
    tmp_dir = tempfile.mkdtemp(prefix="labgen_")

    try:
        # ── Write source file ────────────────────────────────────────────
        src_path = os.path.join(tmp_dir, config["filename"])
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code)

        # ── Compile (if needed) ──────────────────────────────────────────
        if config["compile"]:
            try:
                compile_result = subprocess.run(
                    config["compile"],
                    cwd=tmp_dir,
                    capture_output=True,
                    text=True,
                    timeout=COMPILE_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                return {"stdout": "", "stderr": "Compilation timed out (30s limit)."}
            except FileNotFoundError as exc:
                return {
                    "stdout": "",
                    "stderr": f"Compiler not found: {exc.filename}. "
                    f"Make sure it is installed and on your PATH.",
                }

            if compile_result.returncode != 0:
                return {
                    "stdout": "",
                    "stderr": compile_result.stderr.strip()
                    or compile_result.stdout.strip()
                    or "Compilation failed with no error message.",
                }

        # ── Run ──────────────────────────────────────────────────────────
        try:
            run_result = subprocess.run(
                config["run"],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                timeout=RUN_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": "Execution timed out (30s limit)."}
        except FileNotFoundError as exc:
            return {
                "stdout": "",
                "stderr": f"Runtime not found: {exc.filename}. "
                f"Make sure it is installed and on your PATH.",
            }

        stdout = run_result.stdout.strip()
        stderr = run_result.stderr.strip()

        # Some programs write to stderr for warnings but still succeed
        # Only treat as error if the exit code is non-zero
        if run_result.returncode != 0:
            return {
                "stdout": stdout,
                "stderr": stderr or "Program exited with non-zero code.",
            }

        # Check if plot.png exists and read its bytes before cleanup
        plot_bytes = None
        plot_path = os.path.join(tmp_dir, "plot.png")
        if os.path.exists(plot_path):
            try:
                with open(plot_path, "rb") as f:
                    plot_bytes = f.read()
            except Exception:
                pass

        return {"stdout": stdout, "stderr": "", "plot_png": plot_bytes}

    finally:
        # ── Cleanup temp directory ───────────────────────────────────────
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
