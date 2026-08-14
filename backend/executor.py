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
import re
import subprocess
import tempfile
import shutil
from pathlib import Path

# ── Heavy packages that crash Render free tier (512 MB RAM limit) ─────────────
# Key   = friendly package name shown to user
# Value = list of regex patterns to detect in generated code
HEAVY_PACKAGES: dict[str, list[str]] = {
    "TensorFlow": [
        r"import\s+tensorflow",
        r"from\s+tensorflow",
        r"import\s+tf\b",
    ],
    "PyTorch": [
        r"import\s+torch\b",
        r"from\s+torch",
        r"import\s+torchvision",
        r"import\s+torchaudio",
    ],
    "Keras (standalone)": [
        r"import\s+keras\b",
        r"from\s+keras",
    ],
    "Hugging Face Transformers": [
        r"import\s+transformers",
        r"from\s+transformers",
    ],
    "JAX": [
        r"import\s+jax\b",
        r"from\s+jax",
        r"import\s+jaxlib",
    ],
    "PaddlePaddle": [
        r"import\s+paddle\b",
        r"from\s+paddle",
    ],
    "MXNet": [
        r"import\s+mxnet",
        r"import\s+mx\b",
    ],
}

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


def _detect_heavy_package(code: str) -> str | None:
    """
    Scan code for imports of packages too heavy for the free-tier server.
    Returns the package name if found, else None.
    """
    for package_name, patterns in HEAVY_PACKAGES.items():
        for pattern in patterns:
            if re.search(pattern, code):
                return package_name
    return None


# ── Dangerous code pattern scanner ────────────────────────────────────────────
# Patterns that should NEVER appear in legitimate college lab code
DANGEROUS_CODE_PATTERNS: list[tuple[str, str]] = [
    (r"shutil\.rmtree",              "file/directory deletion (shutil.rmtree)"),
    (r"shutil\.rm",                  "file/directory deletion (shutil.rm)"),
    (r"os\.remove\s*\(",             "file deletion (os.remove)"),
    (r"os\.unlink\s*\(",             "file deletion (os.unlink)"),
    (r"os\.system\s*\(",             "direct OS shell execution (os.system)"),
    (r"subprocess\.(call|run|Popen)","shell subprocess execution"),
    (r"open\(.+,\s*[\"']w[\"']",     "arbitrary file write (open with 'w' mode)"),
    (r"/etc/passwd",                 "access to sensitive system file (/etc/passwd)"),
    (r"/etc/shadow",                 "access to sensitive system file (/etc/shadow)"),
    (r"__import__\s*\(",             "dynamic import execution trick"),
]


def _detect_dangerous_code(code: str) -> str | None:
    """
    Scan generated code for dangerous patterns before execution.
    Returns a human-readable reason string if found, else None.
    """
    for pattern, reason in DANGEROUS_CODE_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            return reason
    return None


def run_code(code: str, language: str) -> dict:
    """
    Execute *code* in a temporary directory and return stdout/stderr.

    Returns a dict with keys:
        stdout (str): Program output.
        stderr (str): Error output (empty string on success).
        plot_png (bytes | None): Plot image bytes if generated.
    """
    # ── Heavy package check ───────────────────────────────────────────────────
    heavy = _detect_heavy_package(code)
    if heavy:
        msg = (
            f"[Server Notice] This experiment uses {heavy}, which requires\n"
            f"more memory than available on the free server.\n"
            f"Please run this experiment locally on your machine\n"
            f"where {heavy} is installed."
        )
        return {"stdout": msg, "stderr": "", "plot_png": None}

    # ── Dangerous code check ──────────────────────────────────────────────────
    dangerous = _detect_dangerous_code(code)
    if dangerous:
        msg = (
            f"[Security Notice] The generated code contains {dangerous},\n"
            f"which is blocked for safety reasons on this server.\n"
            f"Please modify your aim to avoid system-level operations."
        )
        return {"stdout": msg, "stderr": "", "plot_png": None}

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
        # On Linux (production server), run as restricted 'nobody' user
        # to prevent the subprocess from accessing or modifying server files.
        # On Windows (local dev), this parameter is not supported so it is skipped.
        run_kwargs: dict = {
            "cwd":            tmp_dir,
            "capture_output": True,
            "text":           True,
            "timeout":        RUN_TIMEOUT,
        }
        if sys.platform.startswith("linux"):
            try:
                import pwd
                nobody_uid = pwd.getpwnam("nobody").pw_uid
                run_kwargs["user"] = nobody_uid
            except (KeyError, PermissionError):
                pass  # 'nobody' user not available — skip silently

        try:
            run_result = subprocess.run(config["run"], **run_kwargs)
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
