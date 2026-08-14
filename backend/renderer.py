"""
renderer.py — Render terminal output as a PNG using Playwright.

Injects the real project path, run command, and stdout into the
terminal.html mockup, then screenshots it with headless Chromium.

Performance: A single persistent Playwright + Chromium browser instance
is shared across all requests. This avoids the 3-7 second cold-start
penalty of launching a new browser for every generation.
"""

import sys
import textwrap
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser, Playwright

TEMPLATE_PATH = Path(__file__).parent / "templates" / "terminal.html"

# Derive project root (two levels up from this file: backend/ → project root)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# Map language → the command that was actually run by executor.py
LANGUAGE_COMMAND: dict[str, str] = {
    "Python": "python main.py",
    "C": "gcc main.c -o main.exe && main.exe",
    "C++": "g++ main.cpp -o main.exe && main.exe",
    "Java": "javac Main.java && java Main",
    "JavaScript": "node main.js",
    "Rust": "rustc main.rs -o main.exe && main.exe",
}

# ── Persistent browser singleton ───────────────────────────────────────────────
# Launched once on first use, reused for all subsequent requests.
# Auto-reconnects if the browser crashes between requests.

_pw: Playwright | None = None
_browser: Browser | None = None


def _get_browser() -> Browser:
    """
    Return the shared Chromium browser instance, (re)initializing if needed.
    Thread-safety note: FastAPI runs sync routes in a threadpool — for this
    use-case (single-process Render free tier), a module-level singleton is safe.
    """
    global _pw, _browser

    # Re-initialize if browser has never been started or has crashed/disconnected
    if _browser is None or not _browser.is_connected():
        # Clean up stale playwright instance if present
        if _pw is not None:
            try:
                _pw.stop()
            except Exception:
                pass

        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(headless=True)

    return _browser


def _escape_html(text: str) -> str:
    """Escape special HTML characters (pre-wrap handles newlines natively)."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def render_terminal(output: str, language: str = "Python") -> bytes:
    """
    Render captured stdout into a terminal-style PNG.

    The terminal line displayed looks like:
        (.venv) PS C:\\Users\\vaibh\\Desktop\\lab file generator> python main.py

    Args:
        output:   Text to display (stdout from code execution).
        language: Programming language — used to pick the correct run command.

    Returns:
        PNG image bytes of the rendered terminal element.
    """
    command = LANGUAGE_COMMAND.get(language, f"run {language.lower()}")

    # Build the prompt path string:  (.venv) PS C:\path\to\project>
    prompt_path = f"(.venv) PS {PROJECT_ROOT}> "

    # Clean common leading whitespace and outer blank lines
    cleaned_output = textwrap.dedent(output).strip()

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = (
        template.replace("{{PROMPT_PATH}}", _escape_html(prompt_path))
        .replace("{{COMMAND}}", _escape_html(command))
        .replace("{{OUTPUT}}", _escape_html(cleaned_output))
    )

    # Reuse the persistent browser — no cold-start penalty
    browser = _get_browser()
    context = browser.new_context(
        viewport={"width": 960, "height": 800},
        device_scale_factor=2,
    )
    page = context.new_page()
    page.set_content(html, wait_until="load")

    terminal = page.locator("#terminal")
    png_bytes = terminal.screenshot()

    # Close context (frees page memory) but keep the browser alive
    context.close()

    return png_bytes
