"""
renderer.py — Render terminal output as a PNG using Playwright.

Injects the real project path, run command, and stdout into the
terminal.html mockup, then screenshots it with headless Chromium.

Thread Safety:
    Playwright's sync API binds to the greenlet/thread it was started on.
    All Playwright calls MUST happen on the same thread.
    We solve this with a dedicated single-threaded ThreadPoolExecutor
    (_playwright_executor, max_workers=1) — every browser operation is
    submitted to this one thread, so greenlets are always satisfied.
"""

import concurrent.futures
import textwrap
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser, Playwright
from backend.logger import get_logger

logger = get_logger("labgen.renderer")

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

# ── Dedicated Playwright thread ────────────────────────────────────────────────
# max_workers=1 guarantees ALL Playwright calls run on the same OS thread.
# This satisfies Playwright's greenlet binding requirement.
_playwright_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="playwright",
)

_pw: Playwright | None = None
_browser: Browser | None = None


# ── Internal helpers (MUST only be called via _playwright_executor.submit) ─────

def _init_browser() -> Browser:
    """
    Initialize or reconnect the persistent Chromium browser.
    Must only run on the playwright executor thread.
    """
    global _pw, _browser

    if _browser is None or not _browser.is_connected():
        logger.info("Launching headless Chromium browser instance...")
        if _pw is not None:
            try:
                _pw.stop()
            except Exception:
                pass
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(headless=True)
        logger.info("Headless Chromium browser launched successfully.")

    return _browser


def _take_screenshot(html: str) -> bytes:
    """
    Initialize browser (if needed) and take the terminal screenshot.
    Must only run on the playwright executor thread.
    Retries automatically once if browser connection was dropped.
    """
    global _browser, _pw
    for attempt in range(2):
        try:
            browser = _init_browser()
            context = browser.new_context(
                viewport={"width": 960, "height": 800},
                device_scale_factor=1,
            )
            page = context.new_page()
            page.set_content(html, wait_until="domcontentloaded", timeout=10000)

            terminal = page.locator("#terminal")
            png_bytes = terminal.screenshot(timeout=10000)

            context.close()   # free page memory; browser stays alive
            return png_bytes
        except Exception:
            # Reset browser handles on failure to force fresh launch on next attempt
            if _browser:
                try:
                    _browser.close()
                except Exception:
                    pass
                _browser = None
            if _pw:
                try:
                    _pw.stop()
                except Exception:
                    pass
                _pw = None
            if attempt == 1:
                raise


# ── Public API ─────────────────────────────────────────────────────────────────

def warmup_browser() -> None:
    """
    Pre-launch Chromium on the playwright thread at server startup.
    Call this from the FastAPI lifespan so the first user never waits.
    """
    try:
        _playwright_executor.submit(_init_browser).result(timeout=15)
    except Exception:
        pass


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

    Submits the screenshot work to the dedicated playwright thread
    and blocks until the result is ready (max 15 seconds).

    Args:
        output:   Text to display (stdout from code execution).
        language: Programming language — used to pick the correct run command.

    Returns:
        PNG image bytes of the rendered terminal element.
    """
    command = LANGUAGE_COMMAND.get(language, f"run {language.lower()}")
    prompt_path = f"(.venv) PS {PROJECT_ROOT}> "
    cleaned_output = textwrap.dedent(output).strip()

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = (
        template.replace("{{PROMPT_PATH}}", _escape_html(prompt_path))
        .replace("{{COMMAND}}", _escape_html(command))
        .replace("{{OUTPUT}}", _escape_html(cleaned_output))
    )

    # Submit to the single playwright thread and wait for the result (max 15s)
    future = _playwright_executor.submit(_take_screenshot, html)
    return future.result(timeout=15)
